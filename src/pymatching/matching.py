import numpy as np
import networkx as nx
from scipy.sparse import csc_matrix, spmatrix, vstack

from pymatching._cpp_mwpm import (decode, 
                            decode_match_neighbourhood,
                            WeightedStabiliserGraph)


def _find_boundary_nodes(G):
    """Find all boundary nodes in G

    Find the boundary nodes in G, each of which have the attribute
    `is_boundary' set to `True'. Return the indices of the 
    boundary nodes.

    Parameters
    ----------
    G : NetworkX graph
        The stabiliser graph.

    Returns
    -------
    list of int
        The indices of the boundary nodes in G.
    """
    return [i for i, attr in G.nodes(data=True) 
            if attr.get("is_boundary", False)]
    

class Matching:
    """A class for constructing matching graphs and decoding using the minimum-weight perfect matching decoder

    The Matching class provides most of the core functionality of PyMatching. 
    A PyMatching object can be constructed from the :math:`Z` or 
    :math:`X` check matrix of the quantum code, given as a `scipy.sparse` 
    matrix or `numpy.ndarray`, along with additional argument specifying the 
    edge weights, error probabilities and number of repetitions.
    Alternatively, a Matching object can be constructed from a NetworkX 
    graph, with node and edge attributes used to specify edge weights,
    qubit ids, boundaries and error probabilities.
    """
    def __init__(self, H, spacelike_weights=None, 
                 error_probabilities=None, 
                 repetitions=None,
                 timelike_weights=None,
                 measurement_error_probability=None,
                 precompute_shortest_paths=False):
        """Constructor for the Matching class

        Parameters
        ----------
        H : `scipy.spmatrix` or `numpy.ndarray` or `networkx.Graph` object
            The quantum code to be decoded with minimum-weight perfect
            matching, given either as a binary check matrix (scipy sparse 
            matrix or numpy.ndarray), or as a matching graph (NetworkX graph).
            If `H` is given as a NetworkX graph with `M` nodes, each node 
            `m` in `H` should be an integer :math:`0<m<M-1`, and each node should 
            be unique. Each edge in the NetworkX graph can have optional 
            attributes ``qubit_id``, ``weight`` and ``error_probability``. 
            ``qubit_id`` should be an int or a set of ints. If there 
            are :math:`N` qubits then the union of all ints in the ``qubit_id`` 
            attributes in the graph should be the integers :math:`0\ldots N-1`.  
            Each ``weight`` attribute should be a non-negative float. If 
            every edge is assigned an error_probability between zero and one, 
            then the ``add_noise`` method can be used to simulate noise and 
            flip edges independently in the graph.
        spacelike_weights : float or numpy.ndarray, optional
            If `H` is given as a scipy or numpy array, `spacelike_weights` gives the weights
            of edges in the matching graph. By default None, in which case 
            all weights are set to 1.0
        error_probabilities : float or numpy.ndarray, optional
            The probabilities with which an error occurs on each qubit. If a 
            single float is given, the same error probability is used for each 
            qubit. If a numpy.ndarray of floats is given, it must have a 
            length equal to the number of qubits. This parameter is only 
            needed for the Matching.add_noise method, and not for decoding. 
            By default None
        repetitions : int, optional
            The number of times the stabiliser measurements are repeated, if 
            the measurements are noisy. This option is only used if `H` is 
            provided as a check matrix, not a NetworkX graph. By default None
        timelike_weights : float, optional
            If `H` is given as a scipy or numpy array and `repetitions>1`, 
            `timelike_weights` gives the weight of timelike edges. By default 
            None, in which case all weights are set to 1.0
        measurement_error_probability : float, optional
            If `H` is given as a scipy or numpy array and `repetitions>1`, 
            gives the probability of a measurement error to be used for 
            the add_noise method. By default None
        precompute_shortest_paths : bool, optional
            It is almost always recommended to leave this as False. If 
            the exact matching is used for decoding (setting 
            `num_neighbours=None` in `decode`), then setting this option
            to True will precompute the all-pairs shortest paths.
            By default False
        """
        if not isinstance(H, nx.Graph):
            try:
                H = csc_matrix(H)
                unique_elements = np.unique(H.data)
                if len(unique_elements)>1 or unique_elements[0] != 1:
                    raise ValueError("Nonzero elements in the parity check matrix"
                                    f" must be 1, not {unique_elements}.")
                H = H.astype(np.uint8)
            except:
                raise ValueError("H must be a NetworkX graph or convertible "
                                 "to a scipy.csc_matrix")

        if isinstance(H, csc_matrix):
            num_edges = H.shape[1]
        else:
            num_edges = nx.number_of_edges(H)
        
        weights = 1.0 if spacelike_weights is None else spacelike_weights
        if isinstance(weights, (int, float)):
            weights = np.array([weights]*num_edges).astype(float)
        weights = np.asarray(weights)

        if isinstance(H, csc_matrix):
            if error_probabilities is None:
                error_probabilities = np.array([-1]*num_edges)
            elif isinstance(error_probabilities, (int, float)):
                error_probabilities = np.array([error_probabilities]*num_edges)
            column_weights = np.asarray(H.sum(axis=0))[0]
            unique_column_weights = np.unique(column_weights)
            if np.setdiff1d(unique_column_weights, np.array([1,2])).size > 0:
                raise ValueError("Each qubit must be contained in either "
                                 f"1 or 2 check operators, not {unique_column_weights}")
            H.eliminate_zeros()
            H.sort_indices()
            self.num_stabilisers = H.shape[0]
            num_qubits = H.shape[1]

            if weights.shape[0] != num_qubits:
                raise ValueError("Weights array must have num_qubits elements")
            if np.any(weights < 0.):
                raise ValueError("All weights must be non-negative.")
            
            timelike_weights = 1.0 if timelike_weights is None else timelike_weights
            repetitions = 1 if repetitions is None else repetitions
            p_meas = measurement_error_probability if measurement_error_probability is not None else -1
            boundary = [H.shape[0]*repetitions] if 1 in unique_column_weights else []
            self.stabiliser_graph = WeightedStabiliserGraph(H.shape[0]*repetitions, boundary=boundary)
            for t in range(repetitions):
                for i in range(len(H.indptr)-1):
                    s, e = H.indptr[i:i+2]
                    v1 = H.indices[s] + H.shape[0]*t
                    v2 = H.indices[e-1] + H.shape[0]*t if e-s == 2 else boundary[0]
                    self.stabiliser_graph.add_edge(v1, v2, {i}, weights[i], 
                            error_probabilities[i], error_probabilities[i] >= 0)
            for t in range(repetitions-1):
                for i in range(H.shape[0]):
                    self.stabiliser_graph.add_edge(i+t*H.shape[0], i+(t+1)*H.shape[0], 
                            set(), timelike_weights, p_meas, p_meas >= 0)
        else:
            boundary = _find_boundary_nodes(H)
            num_nodes = H.number_of_nodes()
            self.num_stabilisers = num_nodes - len(boundary)
            g = WeightedStabiliserGraph(self.num_stabilisers, boundary)
            for (u, v, attr) in H.edges(data=True):
                qubit_id = attr.get("qubit_id", set())
                if isinstance(qubit_id, (int, np.integer)):
                    qubit_id = {int(qubit_id)} if qubit_id != -1 else set()
                else:
                    try:
                        qubit_id = set(qubit_id)
                        if not all(isinstance(q, (int, np.integer)) for q in qubit_id):
                            raise ValueError(f"qubit_id must be a set of ints, not {qubit_id}")
                    except:
                        raise ValueError("qubit_id property must be an int or a set of int"
                                f" (or convertible to a set), not {qubit_id}")
                weight = attr.get("weight", 1) # Default weight is 1 if not provided
                if weight < 0:
                    raise ValueError("Weights cannot be negative.")
                e_prob = attr.get("error_probability", -1)
                g.add_edge(u, v, qubit_id, weight, e_prob, 0<=e_prob<=1)
            self.stabiliser_graph = g
        if precompute_shortest_paths:
            self.stabiliser_graph.compute_all_pairs_shortest_paths()
    
    @property
    def num_qubits(self):
        return self.stabiliser_graph.get_num_qubits()
    
    @property
    def boundary(self):
        """Return the indices of the boundary nodes

        Returns
        -------
        list of int
            The indices of the boundary nodes
        """
        return self.stabiliser_graph.get_boundary()
    
    def decode(self, z, num_neighbours=20):
        """Decode the syndrome `z` using minimum-weight perfect matching

        Parameters
        ----------
        z : numpy.ndarray
            A binary syndrome vector to decode. The number of elements in 
            `z` should equal the number of nodes in the matching graph. If 
            `z` is a 1D array, then `z[i]` is the syndrome at node `i` of 
            the matching graph. If `z` is 2D then `z[i,j]` is the syndrome 
            of stabiliser `i` in time step `j` (when `repetitions>1`).
        num_neighbours : int, optional
            Number of closest neighbours of each matching graph node to consider 
            when decoding. If `num_neighbours` is set (as it is by default), 
            then the local matching decoder in the Appendix of 
            https://arxiv.org/abs/2010.09626 is used, and `num_neighbours` 
            corresponds to the parameter `m` in the paper. It is recommended 
            to leave `num_neighbours` set to 20, and not to set it to less 
            than 10. If `num_neighbours=None`, then instead full matching is 
            performed, with the all-pairs shortest paths precomputed and 
            cached the first time it is used. Since full matching is more 
            memory intensive, it is not recommended to be used for matching graphs 
            with more than around 10,000 nodes, and is only faster than 
            local matching for matching graphs with less than around 1,000 
            nodes. By default 20

        Returns
        -------
        numpy.ndarray
            A 1D numpy array of ints giving the minimum-weight correction 
            operator. The number of elements equals the number of qubits, 
            and an element is 1 if the corresponding qubit should be flipped, 
            and otherwise 0.

        """
        try:
            z = np.array(z, dtype=np.uint8)
        except:
            raise ValueError("Syndrome must be of type numpy.ndarray or "\
                             f"convertible to numpy.ndarray, not {z}")
        if len(z.shape) == 1 and (self.num_stabilisers <= z.shape[0]
                <= self.num_stabilisers+len(self.boundary)):
            defects = z.nonzero()[0]
        elif len(z.shape) == 2 and z.shape[0] == self.num_stabilisers:
            num_stabs = self.stabiliser_graph.get_num_stabilisers()
            max_num_defects = z.shape[0]*z.shape[1]
            if max_num_defects > num_stabs:
                raise ValueError(f"Syndrome size {z.shape[0]}x{z.shape[1]} exceeds" \
                        f" the number of stabilisers ({num_stabs})")
            times, checks = z.T.nonzero()
            defects = times*self.num_stabilisers + checks
        else:
            raise ValueError(f"The shape ({z.shape}) of the syndrome vector z is not valid.")
        if len(defects) % 2 != 0:
            if len(self.boundary) == 0:
                raise ValueError("Syndrome must contain an even number of defects "
                                    "if no boundary vertex is given.")
            defects = np.setxor1d(defects, np.array(self.boundary[0:1]))
        if num_neighbours is None:
            return decode(self.stabiliser_graph, defects)
        else:
            return decode_match_neighbourhood(self.stabiliser_graph, defects, num_neighbours)
    
    def add_noise(self):
        """Add noise by flipping edges in the stabiliser graph with 
        a probability given by the error_probility edge attribute.
        This is currently only supported for weighted matching graphs
        initialised using a NetworkX graph.

        Returns
        -------
        numpy.ndarray of dtype int
            Noise vector (binary numpy int array of length self.num_qubits)
        numpy.ndarray of dtype int
            Syndrome vector (binary numpy int array of length 
            self.num_stabilisers if there is no boundary, or self.num_stabilisers+1
            if there is a boundary)
        """
        if not self.stabiliser_graph.all_edges_have_error_probabilities:
            return None
        return self.stabiliser_graph.add_noise()
    
    def __repr__(self):
        return f"<pymatching.Matching object with {self.num_qubits} qubits and {self.num_stabilisers} stabilisers>"
