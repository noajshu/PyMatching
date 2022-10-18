# Copyright 2020 Oscar Higgott

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#      http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Union, List, TYPE_CHECKING, Tuple, Set, Dict, Optional
import warnings

import numpy as np
import networkx as nx
import retworkx as rx
import scipy
from scipy.sparse import csc_matrix
import matplotlib.cbook

if TYPE_CHECKING:
    import stim

from pymatching._cpp_pymatching import MatchingGraph as _MatchingGraph
from pymatching._cpp_pymatching import (sparse_column_check_matrix_to_matching_graph,
                                        detector_error_model_to_matching_graph)


class Matching:
    """A class for constructing matching graphs and decoding using the minimum-weight perfect matching decoder.
    The matching graph can be constructed using the `Matching.add_edge` and `Matching.add_boundary_edge`
    methods. Alternatively, it can be loaded from a parity check matrix (a `scipy.sparse` matrix or `numpy.ndarray`
    with one or two non-zero elements in each column), a NetworkX or retworkx graph, or from
    a `stim.DetectorErrorModel`.
    """

    def __init__(self,
                 graph: Union[scipy.sparse.spmatrix, np.ndarray, rx.PyGraph, nx.Graph, List[
                     List[int]], 'stim.DetectorErrorModel'] = None,
                 weights: Union[float, np.ndarray, List[float]] = None,
                 error_probabilities: Union[float, np.ndarray, List[float]] = None,
                 repetitions: int = None,
                 timelike_weights: Union[float, np.ndarray, List[float]] = None,
                 measurement_error_probabilities: Union[float, np.ndarray, List[float]] = None,
                 **kwargs
                 ):
        r"""Constructor for the Matching class
        Parameters
        ----------
        graph : `scipy.spmatrix` or `numpy.ndarray` or `networkx.Graph` or `stim.DetectorErrorModel`, optional
            The matching graph to be decoded with minimum-weight perfect
            matching, given either as a binary parity check matrix (scipy sparse
            matrix or numpy.ndarray), a NetworkX or retworkx graph, or a Stim DetectorErrorModel.
            Each edge in the NetworkX or retworkx graph can have optional
            attributes ``fault_ids``, ``weight`` and ``error_probability``.
            ``fault_ids`` should be an int or a set of ints.
            Each fault id corresponds to a self-inverse fault that is flipped when the
            corresponding edge is flipped. These self-inverse faults could correspond to
            physical Pauli errors (physical frame changes)
            or to the logical observables that are flipped by the fault
            (a logical frame change, equivalent to an obersvable ID in an error instruction in a Stim
            detector error model). The `fault_ids` attribute was previously named `qubit_id` in an
            earlier version of PyMatching, and `qubit_id` is still accepted instead of `fault_ids` in order
            to maintain backward compatibility.
            Each ``weight`` attribute should be a non-negative float. If
            every edge is assigned an error_probability between zero and one,
            then the ``add_noise`` method can be used to simulate noise and
            flip edges independently in the graph. By default, None
        weights : float or numpy.ndarray, optional
            If `graph` is given as a scipy or numpy array, `weights` gives the weights
            of edges in the matching graph corresponding to columns of `graph`.
            If weights is a numpy.ndarray, it should be a 1D array with length
            equal to `graph.shape[1]`. If weights is a float, it is used as the weight for all
            edges corresponding to columns of `graph`. By default None, in which case
            all weights are set to 1.0
            This argument was renamed from `spacelike_weights` in PyMatching v2.0, but
            `spacelike_weights` is still accepted in place of `weights` for backward compatibility.
        error_probabilities : float or numpy.ndarray, optional
            The probabilities with which an error occurs on each edge corresponding
            to a column of the check matrix. If a
            single float is given, the same error probability is used for each
            edge. If a numpy.ndarray of floats is given, it must have a
            length equal to the number of columns in the check matrix. This parameter is only
            needed for the Matching.add_noise method, and not for decoding.
            By default None
        repetitions : int, optional
            The number of times the stabiliser measurements are repeated, if
            the measurements are noisy. This option is only used if `H` is
            provided as a check matrix, not a NetworkX graph. By default None
        timelike_weights : float, optional
            If `H` is given as a scipy or numpy array and `repetitions>1`,
            `timelike_weights` gives the weight of timelike edges.
            If a float is given, all timelike edges weights are set to
            the same value. If a numpy array of size `(H.shape[0],)` is given, the
            edge weight for each vertical timelike edge associated with the `i`th check (row)
            of `H` is set to `timelike_weights[i]`. By default None, in which case all
            timelike weights are set to 1.0
        measurement_error_probabilities : float, optional
            If `H` is given as a scipy or numpy array and `repetitions>1`,
            gives the probability of a measurement error to be used for
            the add_noise method. If a float is given, all measurement
            errors are set to the same value. If a numpy array of size `(H.shape[0],)` is given,
            the error probability for each vertical timelike edge associated with the `i`th check
            (row) of `H` is set to `measurement_error_probabilities[i]`. By default None
        Examples
        --------
        >>> import pymatching
        >>> import math
        >>> m = pymatching.Matching()
        >>> m.add_edge(0, 1, fault_ids={0}, weight=0.1)
        >>> m.add_edge(1, 2, fault_ids={1}, weight=0.15)
        >>> m.add_edge(2, 3, fault_ids={2, 3}, weight=0.2)
        >>> m.add_edge(0, 3, fault_ids={4}, weight=0.1)
        >>> m.set_boundary_nodes({3})
        >>> m
        <pymatching.Matching object with 3 detectors, 1 boundary node, and 4 edges>

        Matching objects can also be created from a check matrix (provided as a scipy.sparse matrix,
        dense numpy array, or list of lists):
        >>> import pymatching
        >>> m = pymatching.Matching([[1, 1, 0, 0], [0, 1, 1, 0], [0, 0, 1, 1]])
        >>> m
        <pymatching.Matching object with 3 detectors, 1 boundary node, and 4 edges>
            """
        self._matching_graph = _MatchingGraph()
        if graph is None:
            graph = kwargs.get("H")
            if graph is None:
                return
            del kwargs["H"]
        if isinstance(graph, nx.Graph):
            self.load_from_networkx(graph)
        elif isinstance(graph, rx.PyGraph):
            self.load_from_retworkx(graph)
        elif type(graph).__name__ == "DetectorErrorModel":
            self.load_from_detector_error_model(graph)
        else:
            try:
                graph = csc_matrix(graph)
            except TypeError:
                raise TypeError("The type of the input graph is not recognised. `graph` must be "
                                "a scipy.sparse or numpy matrix, networkx or retworkx graph, or "
                                "stim.DetectorErrorModel.")
            self.load_from_check_matrix(graph, weights, error_probabilities,
                                        repetitions, timelike_weights, measurement_error_probabilities,
                                        **kwargs)

    def add_noise(self) -> Union[Tuple[np.ndarray, np.ndarray], None]:
        """Add noise by flipping edges in the matching graph with
        a probability given by the error_probility edge attribute.
        The ``error_probability`` must be set for all edges for this
        method to run, otherwise it returns `None`.
        All boundary nodes are always given a 0 syndrome.
        Returns
        -------
        numpy.ndarray of dtype int
            Noise vector (binary numpy int array of length self.num_fault_ids)
        numpy.ndarray of dtype int
            Syndrome vector (binary numpy int array of length
            self.num_detectors if there is no boundary, or self.num_detectors+len(self.boundary)
            if there are boundary nodes)
        """
        if not self._matching_graph.all_edges_have_error_probabilities():
            return None
        return self._matching_graph.add_noise()

    def _syndrome_array_to_detection_events(self, z: Union[np.ndarray, List[int]]) -> np.ndarray:
        try:
            z = np.array(z, dtype=np.uint8)
        except:
            raise TypeError("Syndrome must be of type numpy.ndarray or "
                            "convertible to numpy.ndarray, not {}".format(z))
        if len(z.shape) == 1 and (self.num_detectors <= z.shape[0]
                                  <= self.num_detectors + len(self.boundary)):
            detection_events = z.nonzero()[0]
        elif len(z.shape) == 2 and z.shape[0] * z.shape[1] == self.num_detectors:
            times, checks = z.T.nonzero()
            detection_events = times * z.shape[0] + checks
        else:
            raise ValueError("The shape ({}) of the syndrome vector z is not valid.".format(z.shape))
        return detection_events

    def decode(self,
               z: Union[np.ndarray, List[int]],
               *,
               return_weight: bool = False,
               **kwargs
               ) -> Union[np.ndarray, Tuple[np.ndarray, int]]:
        """Decode the syndrome `z` using minimum-weight perfect matching

        Parameters
        ----------
        z : numpy.ndarray
            A binary syndrome vector to decode. The number of elements in
            `z` should equal the number of nodes in the matching graph. If
            `z` is a 1D array, then `z[i]` is the syndrome at node `i` of
            the matching graph. If `z` is 2D then `z[i,j]` is the difference
            (modulo 2) between the (noisy) measurement of stabiliser `i` in time
            step `j+1` and time step `j` (for the case where the matching graph is
            constructed from a check matrix with `repetitions>1`).
        return_weight : bool, optional
            If `return_weight==True`, the sum of the weights of the edges in the
            minimum weight perfect matching is also returned. By default False
        Returns
        -------
        correction : numpy.ndarray or list[int]
            A 1D numpy array of ints giving the minimum-weight correction operator as a
            binary vector. The number of elements in `correction` is one greater than
            the largest fault ID. The ith element of `correction` is 1 if the
            minimum-weight perfect matching (MWPM) found by PyMatching contains an odd
            number of edges that have `i` as one of the `fault_ids`, and is 0 otherwise.
            If each edge in the matching graph is assigned a unique integer in its
            `fault_ids` attribute, then the locations of nonzero entries in `correction`
            correspond to the edges in the MWPM. However, `fault_ids` can instead be used,
            for example, to store IDs of the physical or logical frame changes that occur
            when an edge flips (see the documentation for ``Matching.add_edge`` for more information).
        weight : float
            Present only if `return_weight==True`.
            The sum of the weights of the edges in the minimum-weight perfect
            matching.
        Raises
        ------
        ValueError
            If there is no error consistent with the provided syndrome. Occurs if the syndrome has odd parity in the
            support of a connected component without a boundary.
        Examples
        --------
        >>> import pymatching
        >>> import numpy as np
        >>> H = np.array([[1, 1, 0, 0, 0],
        ...               [0, 1, 1, 0, 0],
        ...               [0, 0, 1, 1, 0],
        ...               [0, 0, 0, 1, 1]])
        >>> m = pymatching.Matching(H)
        >>> z = np.array([0, 1, 0, 0])
        >>> m.decode(z)
        array([1, 1, 0, 0, 0], dtype=uint8)

        Each bit in the correction provided by Matching.decode corresponds to a
        fault_ids. The index of a bit in a correction corresponds to its fault_ids.
        For example, here an error on edge (0, 1) flips fault_ids 2 and 3, as
        inferred by the minimum-weight correction:
        >>> import pymatching
        >>> m = pymatching.Matching()
        >>> m.add_edge(0, 1, fault_ids={2, 3})
        >>> m.add_edge(1, 2, fault_ids=1)
        >>> m.add_edge(2, 0, fault_ids=0)
        >>> m.decode([1, 1, 0])
        array([0, 0, 1, 1], dtype=uint8)

        To decode with a phenomenological noise model (qubits and measurements both suffering
        bit-flip errors), you can provide a check matrix and number of syndrome repetitions to
        construct a matching graph with a time dimension (where nodes in consecutive time steps
        are connected by an edge), and then decode with a 2D syndrome
        (dimension 0 is space, dimension 1 is time):
        >>> import pymatching
        >>> import numpy as np
        >>> np.random.seed(0)
        >>> H = np.array([[1, 1, 0, 0],
        ...               [0, 1, 1, 0],
        ...               [0, 0, 1, 1]])
        >>> m = pymatching.Matching(H, repetitions=5)
        >>> data_qubit_noise = (np.random.rand(4, 5) < 0.1).astype(np.uint8)
        >>> print(data_qubit_noise)
        [[0 0 0 0 0]
         [0 0 0 0 0]
         [0 0 0 0 1]
         [1 1 0 0 0]]
        >>> cumulative_noise = (np.cumsum(data_qubit_noise, 1) % 2).astype(np.uint8)
        >>> syndrome = H@cumulative_noise % 2
        >>> print(syndrome)
        [[0 0 0 0 0]
         [0 0 0 0 1]
         [1 0 0 0 1]]
        >>> syndrome[:,:-1] ^= (np.random.rand(3, 4) < 0.1).astype(np.uint8)
        >>> # Take the parity of consecutive timesteps to construct a difference syndrome:
        >>> syndrome[:,1:] = syndrome[:,:-1] ^ syndrome[:,1:]
        >>> m.decode(syndrome)
        array([0, 0, 1, 0], dtype=uint8)
        """
        detection_events = self._syndrome_array_to_detection_events(z)
        correction, weight = self._matching_graph.decode(detection_events)
        if return_weight:
            return correction, weight
        else:
            return correction

    def decode_to_matched_dets_array(self,
                                     syndrome: Union[np.ndarray, List[int]]
                                     ) -> Union[np.ndarray, Tuple[np.ndarray, int]]:
        """
        Decode the syndrome `syndrome` using minimum-weight perfect matching, returning the pairs of
        matched detection events (or detection events matched to the boundary) as a 2D numpy array. Note that
        (unlike `Matching.decode`), this method currently only supports non-negative edge weights.

        Parameters
        ----------
        syndrome : numpy.ndarray
            A binary syndrome vector to decode. The number of elements in
            `syndrome` should equal the number of nodes in the matching graph. If
            `syndrome` is a 1D array, then `syndrome[i]` is the syndrome at node `i` of
            the matching graph. If `syndrome` is 2D then `syndrome[i,j]` is the difference
            (modulo 2) between the (noisy) measurement of stabiliser `i` in time
            step `j+1` and time step `j` (for the case where the matching graph is
            constructed from a check matrix with `repetitions>1`).
        Returns
        -------
        numpy.ndarray
            An 2D array `pairs` giving the endpoints of the paths between detection events in the solution of the matching.
            If there are `num_paths` paths then the shape of `pairs` is `num_paths.shape=(num_paths, 2)`, and path `i`
            starts at detection event `pairs[i,0]` and ends at detection event `pairs[i,1]`. For a path `i` connecting
            a detection event to the boundary (either a boundary node or the virtual boundary node), then `pairs[i,0]` is
            is the index of the detection event, and `pairs[i,1]=-1` denotes the boundary.
        >>> import pymatching
        >>> m = pymatching.Matching()
        >>> m.add_boundary_edge(0)
        >>> m.add_edge(0, 1)
        >>> m.add_edge(1, 2)
        >>> m.add_edge(2, 3)
        >>> m.add_edge(3, 4)
        >>> matched_dets = m.decode_to_matched_dets_array([1, 0, 0, 1, 1])
        >>> print(matched_dets)
        [[ 0 -1]
         [ 3  4]]
        """
        detection_events = self._syndrome_array_to_detection_events(syndrome)
        return self._matching_graph.decode_to_matched_detection_events_array(detection_events)

    def decode_to_matched_dets_dict(self,
                                    syndrome: Union[np.ndarray, List[int]]
                                    ) -> Union[np.ndarray, Tuple[np.ndarray, int]]:
        """
        Decode the syndrome `syndrome` using minimum-weight perfect matching, returning a dictionary
        giving the detection event that each detection event was matched to (or None if it was matched
        to the boundary). Note that (unlike `Matching.decode`), this method currently only supports non-negative
        edge weights.

        Parameters
        ----------
        syndrome : numpy.ndarray
            A binary syndrome vector to decode. The number of elements in
            `syndrome` should equal the number of nodes in the matching graph. If
            `syndrome` is a 1D array, then `syndrome[i]` is the syndrome at node `i` of
            the matching graph. If `syndrome` is 2D then `syndrome[i,j]` is the difference
            (modulo 2) between the (noisy) measurement of stabiliser `i` in time
            step `j+1` and time step `j` (for the case where the matching graph is
            constructed from a check matrix with `repetitions>1`).
        Returns
        -------
        dict
            A dictionary `mate` giving the detection event that each detection event is matched to (or `None` if
            it is matched to the boundary). If detection event `i` is matched to detection event `j`, then
            `mate[i]=j`. If detection event `i` is matched to the boundary (either a boundary node or the virtual boundary
            node), then `mate[i]=None`.
        >>> import pymatching
        >>> m = pymatching.Matching()
        >>> m.add_boundary_edge(0)
        >>> m.add_edge(0, 1)
        >>> m.add_edge(1, 2)
        >>> m.add_edge(2, 3)
        >>> m.add_edge(3, 4)
        >>> d = m.decode_to_matched_dets_dict([1, 0, 0, 1, 1])
        >>> d[3]
        4
        >>> d
        {0: None, 3: 4, 4: 3}
        """
        detection_events = self._syndrome_array_to_detection_events(syndrome)
        return self._matching_graph.decode_to_matched_detection_events_dict(detection_events)

    def draw(self) -> None:
        """Draw the matching graph using matplotlib
        Draws the matching graph as a matplotlib graph. Stabiliser nodes are
        filled grey and boundary nodes are filled white. The line thickness of each
        edge is determined from its weight (with min and max thicknesses of 0.2 pts
        and 2 pts respectively).
        Note that you may need to call `plt.figure()` before and `plt.show()` after calling
        this function.
        """
        # Ignore matplotlib deprecation warnings from networkx.draw_networkx
        warnings.filterwarnings("ignore", category=matplotlib.cbook.mplDeprecation)
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        G = self.to_networkx()
        pos = nx.spectral_layout(G, weight=None)
        c = "#bfbfbf"
        ncolors = ['w' if n[1]['is_boundary'] else c for n in G.nodes(data=True)]
        nx.draw_networkx_nodes(G, pos=pos, node_color=ncolors, edgecolors=c)
        nx.draw_networkx_labels(G, pos=pos)
        weights = np.array([e[2]['weight'] for e in G.edges(data=True)])
        normalised_weights = 0.2 + 2 * weights / np.max(weights)
        nx.draw_networkx_edges(G, pos=pos, width=normalised_weights)

        def qid_to_str(qid):
            if len(qid) == 0:
                return ""
            elif len(qid) == 1:
                return str(qid.pop())
            else:
                return str(qid)

        edge_labels = {(s, t): qid_to_str(d['fault_ids']) for (s, t, d) in G.edges(data=True)}
        nx.draw_networkx_edge_labels(G, pos=pos, edge_labels=edge_labels)

    def __repr__(self) -> str:
        m = self.num_detectors
        b = len(self.boundary)
        e = self._matching_graph.get_num_edges()
        return "<pymatching.Matching object with " \
               "{} detector{}, " \
               "{} boundary node{}, " \
               "and {} edge{}>".format(
            m, 's' if m != 1 else '', b, 's' if b != 1 else '',
            e, 's' if e != 1 else '')

    def add_edge(
            self,
            node1: int,
            node2: int,
            fault_ids: Union[int, Set[int]] = None,
            weight: float = 1.0,
            error_probability: float = None,
            *,
            merge_strategy: str = "disallow",
            **kwargs
    ) -> None:
        """
        Add an edge to the matching graph
        Parameters
        ----------
        node1: int
            The index of node1 in the new edge (node1, node2)
        node2: int
            The index of node2 in the new edge (node1, node2)
        fault_ids: set[int] or int, optional
            The indices of any self-inverse faults which are flipped when the edge is flipped, and which should be tracked.
            This could correspond to the IDs of physical Pauli errors that occur when this
            edge flips (physical frame changes). Alternatively,
            this attribute can be used to store the IDs of any logical observables that are
            flipped when an error occurs on an edge (logical frame changes). In earlier versions of PyMatching, this
            attribute was instead named `qubit_id` (since for CSS codes and physical frame changes, there can be
            a one-to-one correspondence between each fault ID and physical qubit ID). For backward
            compatibility, `qubit_id` can still be used instead of `fault_ids` as a keyword argument.
            By default None
        weight: float, optional
            The weight of the edge, which must be non-negative, by default 1.0
        error_probability: float, optional
            The probability that the edge is flipped. This is used by the `add_noise()` method
            to sample from the distribution defined by the matching graph (in which each edge
            is flipped independently with the corresponding `error_probability`). By default None
        merge_strategy: str, optional
            Which strategy to use if the edge (`node1`, `node2`) is already in the graph. The available options
            are "disallow", "independent", "smallest-weight", "keep-original" and "replace". "disallow" raises a
            `ValueError` if the edge (`node1`, `node2`) is already present. The "independent" strategy assumes that
            the existing edge (`node1`, `node2`) and the edge being added represent independent error mechanisms, and
            they are merged into a new edge with updated weights and error_probabilities accordingly (it is assumed
            that each weight represents the log-likelihood ratio log((1-p)/p) where p is the `error_probability` and
            where the natural logarithm is used. The fault_ids associated with the existing edge are kept only, since
            where the natural logarithm is used. The fault_ids associated with the existing edge are kept only, since
            the code has distance 2 if parallel edges have different fault_ids anyway). The "smallest-weight" strategy
            keeps only the new edge if it has a smaller weight than the existing edge, otherwise the graph is left
            unchanged. The "keep-original" strategy keeps only the existing edge, and ignores the edge being added.
            The "replace" strategy always keeps the edge being added, replacing the existing edge.
            By default, "disallow"
        Examples
        --------
        >>> import pymatching
        >>> m = pymatching.Matching()
        >>> m.add_edge(0, 1)
        >>> m.add_edge(1, 2)
        >>> print(m.num_edges)
        2
        >>> print(m.num_nodes)
        3
        >>> import math
        >>> m = pymatching.Matching()
        >>> m.add_edge(0, 1, fault_ids=2, weight=math.log((1-0.05)/0.05), error_probability=0.05)
        >>> m.add_edge(1, 2, fault_ids=0, weight=math.log((1-0.1)/0.1), error_probability=0.1)
        >>> m.add_edge(2, 0, fault_ids={1, 2}, weight=math.log((1-0.2)/0.2), error_probability=0.2)
        >>> m
        <pymatching.Matching object with 3 detectors, 0 boundary nodes, and 3 edges>
        >>> m = pymatching.Matching()
        >>> m.add_edge(0, 1, fault_ids=0, weight=2)
        >>> m.add_edge(0, 1, fault_ids=1, weight=1, merge_strategy="smallest-weight")
        >>> m.add_edge(0, 1, fault_ids=2, weight=3, merge_strategy="smallest-weight")
        >>> m.edges()
        [(0, 1, {'fault_ids': {1}, 'weight': 1.0, 'error_probability': -1.0})]
        """
        if fault_ids is not None and "qubit_id" in kwargs:
            raise ValueError("Both `fault_ids` and `qubit_id` were provided as arguments. Please "
                             "provide `fault_ids` instead of `qubit_id` as an argument, as use of `qubit_id` has "
                             "been deprecated.")
        if fault_ids is None and "qubit_id" in kwargs:
            fault_ids = kwargs["qubit_id"]
        if isinstance(fault_ids, (int, np.integer)):
            fault_ids = set() if fault_ids == -1 else {int(fault_ids)}
        fault_ids = set() if fault_ids is None else fault_ids
        error_probability = error_probability if error_probability is not None else -1
        self._matching_graph.add_edge(node1, node2, fault_ids, weight,
                                      error_probability, merge_strategy)

    def add_boundary_edge(
            self,
            node: int,
            fault_ids: Union[int, Set[int]] = None,
            weight: float = 1.0,
            error_probability: float = None,
            *,
            merge_strategy: str = "disallow",
            **kwargs
    ) -> None:
        """
        Add an edge connecting `node` to the boundary

        Parameters
        ----------
        node: int
            The index of the node to be connected to the boundary with a boundary edge
        fault_ids: set[int] or int, optional
            The IDs of any self-inverse faults which are flipped when the edge is flipped, and which should be tracked.
            This could correspond to the IDs of physical Pauli errors that occur when this
            edge flips (physical frame changes). Alternatively,
            this attribute can be used to store the IDs of any logical observables that are
            flipped when an error occurs on an edge (logical frame changes). By default None
        weight: float, optional
            The weight of the edge, which must be non-negative, by default 1.0
        error_probability: float, optional
            The probability that the edge is flipped. This is used by the `add_noise()` method
            to sample from the distribution defined by the matching graph (in which each edge
            is flipped independently with the corresponding `error_probability`). By default None
        merge_strategy: str, optional
            Which strategy to use if the edge (`node1`, `node2`) is already in the graph. The available options
            are "disallow", "independent", "smallest-weight", "keep-original" and "replace". "disallow" raises a
            `ValueError` if the edge (`node1`, `node2`) is already present. The "independent" strategy assumes that
            the existing edge (`node1`, `node2`) and the edge being added represent independent error mechanisms, and
            they are merged into a new edge with updated weights and error_probabilities accordingly (it is assumed
            that each weight represents the log-likelihood ratio log((1-p)/p) where p is the `error_probability` and
            where the natural logarithm is used. The fault_ids associated with the existing edge are kept only, since
            where the natural logarithm is used. The fault_ids associated with the existing edge are kept only, since
            the code has distance 2 if parallel edges have different fault_ids anyway). The "smallest-weight" strategy
            keeps only the new edge if it has a smaller weight than the existing edge, otherwise the graph is left
            unchanged. The "keep-original" strategy keeps only the existing edge, and ignores the edge being added.
            The "replace" strategy always keeps the edge being added, replacing the existing edge.
            By default, "disallow"
        Examples
        --------
        >>> import pymatching
        >>> m = pymatching.Matching()
        >>> m.add_boundary_edge(0)
        >>> m.add_edge(0, 1)
        >>> print(m.num_edges)
        2
        >>> print(m.num_nodes)
        2
        >>> import math
        >>> m = pymatching.Matching()
        >>> m.add_boundary_edge(0, fault_ids={0}, weight=math.log((1-0.05)/0.05), error_probability=0.05)
        >>> m.add_edge(0, 1, fault_ids={1}, weight=math.log((1-0.1)/0.1), error_probability=0.1)
        >>> m.add_boundary_edge(1, fault_ids={2}, weight=math.log((1-0.2)/0.2), error_probability=0.2)
        >>> m
        <pymatching.Matching object with 2 detectors, 0 boundary nodes, and 3 edges>
        >>> m = pymatching.Matching()
        >>> m.add_boundary_edge(0, fault_ids=0, weight=2)
        >>> m.add_boundary_edge(0, fault_ids=1, weight=1, merge_strategy="smallest-weight")
        >>> m.add_boundary_edge(0, fault_ids=2, weight=3, merge_strategy="smallest-weight")
        >>> m.edges()
        [(0, None, {'fault_ids': {1}, 'weight': 1.0, 'error_probability': -1.0})]
        >>> m.boundary  # Using Matching.add_boundary_edge, no boundary nodes are added (the boundary is a virtual node)
        set()
        """
        if isinstance(fault_ids, (int, np.integer)):
            fault_ids = set() if fault_ids == -1 else {int(fault_ids)}
        fault_ids = set() if fault_ids is None else fault_ids
        error_probability = error_probability if error_probability is not None else -1
        self._matching_graph.add_boundary_edge(node, fault_ids, weight,
                                               error_probability, merge_strategy)

    def has_edge(self, node1: int, node2: int) -> bool:
        """
        Returns True if edge `(node1, node2)` is in the graph.

        Parameters
        ----------
        node1: int
            The index of the first node
        node2: int
            The index of the second node

        Returns
        -------
        bool
            True if the edge `(node1, node2)` is in the graph, otherwise False.
        """
        return self._matching_graph.has_edge(node1, node2)

    def has_boundary_edge(self, node: int) -> bool:
        """
        Returns True if the boundary edge `(node,)` is in the graph. Note: this method does
        not check if `node` is connected to a boundary node in `Matching.boundary`; it only
        checks if `node` is connected to the virtual boundary node (i.e. whether there is a boundary
        edge `(node,)` present).

        Parameters
        ----------
        node: int
            The index of the node

        Returns
        -------
        bool
            True if the boundary edge `(node,)` is present, otherwise False.

        """
        return self._matching_graph.has_boundary_edge(node)

    def get_edge_data(self, node1: int, node2: int) -> Dict[str, Union[Set[int], float]]:
        """
        Returns the edge data associated with the edge `(node1, node2)`.

        Parameters
        ----------
        node1: int
            The index of the first node
        node2: int
            The index of the second node

        Returns
        -------
        dict
            A dictionary with keys `fault_ids`, `weight` and `error_probability`, and values giving the respective
            edge attributes
        """
        return self._matching_graph.get_edge_data(node1, node2)

    def get_boundary_edge_data(self, node: int) -> Dict[str, Union[Set[int], float]]:
        """
        Returns the edge data associated with the boundary edge `(node,)`.

        Parameters
        ----------
        node: int
            The index of the node

        Returns
        -------
        dict
            A dictionary with keys `fault_ids`, `weight` and `error_probability`, and values giving the respective
            boundary edge attributes
        """
        return self._matching_graph.get_boundary_edge_data(node)

    def edges(self) -> List[Tuple[int, Optional[int], Dict]]:
        """Edges of the matching graph
        Returns a list of edges of the matching graph. Each edge is a
        tuple `(source, target, attr)` where `source` and `target` are ints corresponding to the
        indices of the source and target nodes, and `attr` is a dictionary containing the
        attributes of the edge.
        The dictionary `attr` has keys `fault_ids` (a set of ints), `weight` (the weight of the edge,
        set to 1.0 if not specified), and `error_probability`
        (the error probability of the edge, set to -1 if not specified).
        Returns
        -------
        List of (int, int, dict) tuples
            A list of edges of the matching graph
        """
        return self._matching_graph.get_edges()

    def load_from_check_matrix(self,
                               H: Union[scipy.sparse.spmatrix, np.ndarray, List[List[int]]],
                               weights: Union[float, np.ndarray, List[float]] = None,
                               error_probabilities: Union[float, np.ndarray, List[float]] = None,
                               repetitions: int = None,
                               timelike_weights: Union[float, np.ndarray, List[float]] = None,
                               measurement_error_probabilities: Union[float, np.ndarray, List[float]] = None,
                               *,
                               merge_strategy: str = "smallest-weight",
                               use_virtual_boundary_node: bool = False,
                               **kwargs
                               ) -> None:
        """
        Load a matching graph from a check matrix
        Parameters
        ----------
        H : `scipy.spmatrix` or `numpy.ndarray` or List[List[int]]
            The quantum code to be decoded with minimum-weight perfect
            matching, given as a binary check matrix (scipy sparse
            matrix or numpy.ndarray)
        weights : float or numpy.ndarray, optional
            If `H` is given as a scipy or numpy array, `weights` gives the weights
            of edges in the matching graph corresponding to columns of `H`.
            If `weights` is a numpy.ndarray, it should be a 1D array with length
            equal to `H.shape[1]`. If weights is a float, it is used as the weight for all
            edges corresponding to columns of `H`. By default None, in which case
            all weights are set to 1.0
            This argument was renamed from `spacelike_weights` in PyMatching v2.0, but
            `spacelike_weights` is still accepted in place of `weights` for backward compatibility.
        error_probabilities : float or numpy.ndarray, optional
            The probabilities with which an error occurs on each edge associated with a
            column of H. If a
            single float is given, the same error probability is used for each
            column. If a numpy.ndarray of floats is given, it must have a
            length equal to the number of columns in H. This parameter is only
            needed for the Matching.add_noise method, and not for decoding.
            By default None
        repetitions : int, optional
            The number of times the stabiliser measurements are repeated, if
            the measurements are noisy. By default None
        timelike_weights : float or numpy.ndarray, optional
            If `repetitions>1`, `timelike_weights` gives the weight of
            timelike edges. If a float is given, all timelike edges weights are set to
            the same value. If a numpy array of size `(H.shape[0],)` is given, the
            edge weight for each vertical timelike edge associated with the `i`th check (row)
            of `H` is set to `timelike_weights[i]`. By default None, in which case all
            timelike weights are set to 1.0
        measurement_error_probabilities : float or numpy.ndarray, optional
            If `repetitions>1`, gives the probability of a measurement
            error to be used for the add_noise method. If a float is given, all measurement
            errors are set to the same value. If a numpy array of size `(H.shape[0],)` is given,
            the error probability for each vertical timelike edge associated with the `i`th check
            (row) of `H` is set to `measurement_error_probabilities[i]`. This argument can also be
            given using the keyword argument `measurement_error_probability` to maintain backward
            compatibility with previous versions of Pymatching. By default None
        merge_strategy: str, optional
            Which strategy to use when adding an edge (`node1`, `node2`) that is already in the graph. The available
            options are "disallow", "independent", "smallest-weight", "keep-original" and "replace". "disallow" raises a
            `ValueError` if the edge (`node1`, `node2`) is already present. The "independent" strategy assumes that
            the existing edge (`node1`, `node2`) and the edge being added represent independent error mechanisms, and
            they are merged into a new edge with updated weights and error_probabilities accordingly (it is assumed
            that each weight represents the log-likelihood ratio log((1-p)/p) where p is the `error_probability` and
            where the natural logarithm is used. The fault_ids associated with the existing edge are kept only, since
            the code has distance 2 if parallel edges have different fault_ids anyway). The "smallest-weight" strategy
            keeps only the new edge if it has a smaller weight than the existing edge, otherwise the graph is left
            unchanged. The "keep-original" strategy keeps only the existing edge, and ignores the edge being added.
            The "replace" strategy always keeps the edge being added, replacing the existing edge.
            By default, "smallest-weight"
        use_virtual_boundary_node: bool, optional
            This option determines how columns are handled if they contain only a single 1 (representing a boundary edge).
            Consider a column contains a single 1 at row index i. If `use_virtual_boundary_node=False`, then this column
            will be handled by adding an edge `(i, H.shape[0])`, and marking the node `H.shape[0]` as a boundary node with
            `Matching.set_boundary(H.shape[0])`. The resulting graph will contain `H.shape[0]+1` nodes, the largest of
            which is the boundary node. If `use_virtual_boundary_node=True` then instead the boundary is a virtual node, and
            this column is handled with `Matching.add_boundary_edge(i, ...)`. The resulting graph will contain `H.shape[0]`
            nodes, and there is no boundary node. Both options are handled identically by the decoder, although
            `use_virtual_boundary_node=True` is recommended since it is simpler (with a one-to-one correspondence between
             nodes and rows of H), and is also slightly more efficient. By default, False (for backward compatibility)
        Examples
        --------
        >>> import pymatching
        >>> m = pymatching.Matching([[1, 1, 0, 0], [0, 1, 1, 0], [0, 0, 1, 1]])
        >>> m
        <pymatching.Matching object with 3 detectors, 1 boundary node, and 4 edges>

        Matching objects can also be initialised from a sparse scipy matrix:
        >>> import pymatching
        >>> from scipy.sparse import csc_matrix
        >>> H = csc_matrix([[1, 1, 0], [0, 1, 1]])
        >>> m = pymatching.Matching(H)
        >>> m
        <pymatching.Matching object with 2 detectors, 1 boundary node, and 3 edges>
        """
        if not isinstance(H, csc_matrix):
            try:
                H = csc_matrix(H)
            except TypeError:
                raise TypeError("H must be convertible to a `scipy.csc_matrix`")
        num_edges = H.shape[1]

        slw = kwargs.get("spacelike_weights")
        if weights is None and slw is not None:
            weights = slw
        elif weights is not None and slw is not None:
            raise ValueError("Both `weights` and `spacelike_weights` were provided as arguments, but these "
                             "two arguments are equivalent. Please provide only `weights` as an argument, as "
                             "the `spacelike_weights` argument has been deprecated.")

        weights = 1.0 if weights is None else weights
        if isinstance(weights, (int, float, np.integer, np.floating)):
            weights = np.ones(num_edges, dtype=float) * weights
        weights = np.asarray(weights)

        if error_probabilities is None:
            error_probabilities = np.ones(num_edges) * -1
        elif isinstance(error_probabilities, (int, float)):
            error_probabilities = np.ones(num_edges) * error_probabilities

        H.eliminate_zeros()

        repetitions = 1 if repetitions is None else repetitions

        if repetitions > 1:
            timelike_weights = 1.0 if timelike_weights is None else timelike_weights
            if isinstance(timelike_weights, (int, float, np.integer, np.floating)):
                timelike_weights = np.ones(H.shape[0], dtype=float) * timelike_weights
            elif isinstance(timelike_weights, (np.ndarray, list)):
                timelike_weights = np.array(timelike_weights, dtype=float)
            else:
                raise ValueError("timelike_weights should be a float or a 1d numpy array")

            mep = kwargs.get("measurement_error_probability")
            if measurement_error_probabilities is not None and mep is not None:
                raise ValueError("Both `measurement_error_probabilities` and `measurement_error_probability` "
                                 "were provided as arguments. Please "
                                 "provide `measurement_error_probabilities` instead of `measurement_error_probability` "
                                 "as an argument, as use of `measurement_error_probability` has been deprecated.")
            if measurement_error_probabilities is None and mep is not None:
                measurement_error_probabilities = mep

            p_meas = measurement_error_probabilities if measurement_error_probabilities is not None else -1
            if isinstance(p_meas, (int, float, np.integer, np.floating)):
                p_meas = np.ones(H.shape[0], dtype=float) * p_meas
            elif isinstance(p_meas, (np.ndarray, list)):
                p_meas = np.array(p_meas, dtype=float)
            else:
                raise ValueError("measurement_error_probabilities should be a float or 1d numpy array")
        else:
            timelike_weights = None
            p_meas = None

        self._matching_graph = sparse_column_check_matrix_to_matching_graph(H, weights, error_probabilities,
                                                                            merge_strategy,
                                                                            use_virtual_boundary_node, repetitions,
                                                                            timelike_weights, p_meas)

    def load_from_detector_error_model(self, model: 'stim.DetectorErrorModel') -> None:
        """
        Load from a `stim.DetectorErrorModel`.

        A `stim.DetectorErrorModel` (DEM) describes a circuit-level noise model in a quantum error correction protocol,
        and is defined in the
        Stim documentation: https://github.com/quantumlib/Stim/blob/main/doc/file_format_dem_detector_error_model.md.
        When loading from a DEM, there is a one-to-one correspondence with a detector in the DEM and a
        node in the `pymatching.Matching` graph, and each graphlike error in the DEM becomes an edge (or merged into
        a parallel edge) in the `pymatching.Matching` graph.
        A error instruction in the DEM is graphlike if it causes either one or two detection events, and can be
        either its own DEM instruction, or within a suggested decomposition of a larger DEM instruction.
        Error instruction in the DEM that cause more than two detection events and do not have a suggested
        decomposition into edges are ignored.
        There set of `fault_ids` assigned to a `pymatching.Matching` graph edge is the set of
        `logical_observable` indices associated with the corresponding graphlike fault mechanism in the DEM.
        Parallel edges are merged, with weights chosen on the assumption that the error mechanisms associated with the
        parallel edges are independent.
        If parallel edges have different `logical_observable` indices, this implies the code has distance 2, and only
         the `logical_observable` indices associated with the first added parallel edge are kept for the merged edge.
        If you are loading a `pymatching.Matching` graph from a DEM, you may be interested in
        using the sinter Python package for monte carlo sampling: https://pypi.org/project/sinter/.
        Parameters
        ----------
        model

        Returns
        -------

        """
        try:
            import stim
        except ImportError as ex:
            raise ImportError(
                "The 'stim' package isn't installed and is required for this method. \n"
                "To install stim using pip, run `pip install stim`."
            ) from ex
        if not isinstance(model, stim.DetectorErrorModel):
            raise ValueError(f"'model' must be `stim.DetectorErrorModel`. Instead, got: {type(model)}")
        self._matching_graph = detector_error_model_to_matching_graph(str(model))

    def load_from_networkx(self, graph: nx.Graph, *, min_num_fault_ids: int = None) -> None:
        r"""
        Load a matching graph from a NetworkX graph
        Parameters
        ----------
        graph : networkx.Graph
            Each edge in the NetworkX graph can have optional
            attributes ``fault_ids``, ``weight`` and ``error_probability``.
            ``fault_ids`` should be an int or a set of ints.
            Each fault id corresponds to a self-inverse fault that is flipped when the
            corresponding edge is flipped. These self-inverse faults could correspond to
            physical Pauli errors (physical frame changes)
            or to the logical observables that are flipped by the fault
            (a logical frame change, equivalent to an obersvable ID in an error instruction in a Stim
            detector error model). The `fault_ids` attribute was previously named `qubit_id` in an
            earlier version of PyMatching, and `qubit_id` is still accepted instead of `fault_ids` in order
            to maintain backward compatibility.
            Each ``weight`` attribute should be a non-negative float. If
            every edge is assigned an error_probability between zero and one,
            then the ``add_noise`` method can be used to simulate noise and
            flip edges independently in the graph.
        min_num_fault_ids: int
            Sets the minimum number of fault ids in the matching graph. Let `max_id` be the maximum fault id assigned to
            any of the edges in the graph. Then setting this argument will ensure that
            `Matching.num_fault_ids=max(min_num_fault_ids, max_id)`. Note that `Matching.num_fault_ids` sets the length
            of the correction array output by `Matching.decode`.
        Examples
        --------
        >>> import pymatching
        >>> import networkx as nx
        >>> import math
        >>> g = nx.Graph()
        >>> g.add_edge(0, 1, fault_ids=0, weight=math.log((1-0.1)/0.1), error_probability=0.1)
        >>> g.add_edge(1, 2, fault_ids=1, weight=math.log((1-0.15)/0.15), error_probability=0.15)
        >>> g.nodes[0]['is_boundary'] = True
        >>> g.nodes[2]['is_boundary'] = True
        >>> m = pymatching.Matching(g)
        >>> m
        <pymatching.Matching object with 1 detector, 2 boundary nodes, and 2 edges>
        """

        if not isinstance(graph, nx.Graph):
            raise TypeError("G must be a NetworkX graph")
        boundary = {i for i, attr in graph.nodes(data=True)
                    if attr.get("is_boundary", False)}
        num_nodes = graph.number_of_nodes()
        all_fault_ids = set()
        num_fault_ids = 0 if min_num_fault_ids is None else min_num_fault_ids
        g = _MatchingGraph(num_nodes, num_fault_ids)
        g.set_boundary(boundary)
        for (u, v, attr) in graph.edges(data=True):
            u, v = int(u), int(v)
            if "fault_ids" in attr and "qubit_id" in attr:
                raise ValueError("Both `fault_ids` and `qubit_id` were provided as edge attributes, however use "
                                 "of `qubit_id` has been deprecated in favour of `fault_ids`. Please only supply "
                                 "`fault_ids` as an edge attribute.")
            if "fault_ids" not in attr and "qubit_id" in attr:
                fault_ids = attr["qubit_id"]  # Still accept qubit_id as well for now
            else:
                fault_ids = attr.get("fault_ids", set())
            if isinstance(fault_ids, (int, np.integer)):
                fault_ids = {int(fault_ids)} if fault_ids != -1 else set()
            else:
                try:
                    fault_ids = set(fault_ids)
                    if not all(isinstance(q, (int, np.integer)) for q in fault_ids):
                        raise ValueError("fault_ids must be a set of ints, not {}".format(fault_ids))
                except:
                    raise ValueError(
                        "fault_ids property must be an int or a set of int" \
                        " (or convertible to a set), not {}".format(fault_ids))
            all_fault_ids = all_fault_ids | fault_ids
            weight = attr.get("weight", 1)  # Default weight is 1 if not provided
            e_prob = attr.get("error_probability", -1)
            # Note: NetworkX graphs do not support parallel edges (merge strategy is redundant)
            g.add_edge(u, v, fault_ids, weight, e_prob, merge_strategy="smallest-weight")
        self._matching_graph = g

    def load_from_retworkx(self, graph: rx.PyGraph, *, min_num_fault_ids: int = None) -> None:
        r"""
        Load a matching graph from a retworkX graph
        Parameters
        ----------
        graph : retworkx.PyGraph
            Each edge in the retworkx graph can have dictionary payload with keys
            ``fault_ids``, ``weight`` and ``error_probability``. ``fault_ids`` should be
            an int or a set of ints. Each fault id corresponds to a self-inverse fault
            that is flipped when the corresponding edge is flipped. These self-inverse
            faults could correspond to physical Pauli errors (physical frame changes)
            or to the logical observables that are flipped by the fault
            (a logical frame change, equivalent to an obersvable ID in an error instruction in a Stim
            detector error model). The `fault_ids` attribute was previously named `qubit_id` in an
            earlier version of PyMatching, and `qubit_id` is still accepted instead of `fault_ids` in order
            to maintain backward compatibility.
            Each ``weight`` attribute should be a non-negative float. If
            every edge is assigned an error_probability between zero and one,
            then the ``add_noise`` method can be used to simulate noise and
            flip edges independently in the graph.
        min_num_fault_ids: int
            Sets the minimum number of fault ids in the matching graph. Let `max_id` be the maximum fault id assigned to
            any of the edges in the graph. Then setting this argument will ensure that
            `Matching.num_fault_ids=max(min_num_fault_ids, max_id)`. Note that `Matching.num_fault_ids` sets the length
            of the correction array output by `Matching.decode`.
        Examples
        --------
        >>> import pymatching
        >>> import retworkx as rx
        >>> import math
        >>> g = rx.PyGraph()
        >>> matching = g.add_nodes_from([{} for _ in range(3)])
        >>> edge_a =g.add_edge(0, 1, dict(fault_ids=0, weight=math.log((1-0.1)/0.1), error_probability=0.1))
        >>> edge_b = g.add_edge(1, 2, dict(fault_ids=1, weight=math.log((1-0.15)/0.15), error_probability=0.15))
        >>> g[0]['is_boundary'] = True
        >>> g[2]['is_boundary'] = True
        >>> m = pymatching.Matching(g)
        >>> m
        <pymatching.Matching object with 1 detector, 2 boundary nodes, and 2 edges>
        """
        if not isinstance(graph, rx.PyGraph):
            raise TypeError("G must be a retworkx graph")
        boundary = {i for i in graph.node_indices() if graph[i].get("is_boundary", False)}
        num_nodes = len(graph)
        num_fault_ids = 0 if min_num_fault_ids is None else min_num_fault_ids
        g = _MatchingGraph(num_nodes, num_fault_ids)
        g.set_boundary(boundary)
        for (u, v, attr) in graph.weighted_edge_list():
            u, v = int(u), int(v)
            if "fault_ids" in attr and "qubit_id" in attr:
                raise ValueError("Both `fault_ids` and `qubit_id` were provided as edge attributes, however use "
                                 "of `qubit_id` has been deprecated in favour of `fault_ids`. Please only supply "
                                 "`fault_ids` as an edge attribute.")
            if "fault_ids" not in attr and "qubit_id" in attr:
                fault_ids = attr["qubit_id"]  # Still accept qubit_id as well for now
            else:
                fault_ids = attr.get("fault_ids", set())
            if isinstance(fault_ids, (int, np.integer)):
                fault_ids = {int(fault_ids)} if fault_ids != -1 else set()
            else:
                try:
                    fault_ids = set(fault_ids)
                    if not all(isinstance(q, (int, np.integer)) for q in fault_ids):
                        raise ValueError("fault_ids must be a set of ints, not {}".format(fault_ids))
                except:
                    raise ValueError(
                        "fault_ids property must be an int or a set of int" \
                        " (or convertible to a set), not {}".format(fault_ids))
            weight = attr.get("weight", 1)  # Default weight is 1 if not provided
            e_prob = attr.get("error_probability", -1)
            # Note: retworkx graphs do not support parallel edges (merge strategy is redundant)
            g.add_edge(u, v, fault_ids, weight, e_prob, merge_strategy="smallest-weight")
        self._matching_graph = g

    def to_networkx(self) -> nx.Graph:
        """Convert to NetworkX graph
        Returns a NetworkX graph corresponding to the matching graph. Each edge
        has attributes `fault_ids`, `weight` and `error_probability` and each node has
        the attribute `is_boundary`.
        Returns
        -------
        NetworkX.Graph
            NetworkX Graph corresponding to the matching graph
        """
        G = nx.Graph()
        G.add_edges_from(self.edges())
        boundary = self.boundary
        for i in G.nodes:
            is_boundary = i in boundary
            G.nodes[i]['is_boundary'] = is_boundary
        return G

    def to_retworkx(self) -> rx.PyGraph:
        """Convert to retworkx graph
        Returns a retworkx graph object corresponding to the matching graph. Each edge
        payload is a ``dict`` with keys `fault_ids`, `weight` and `error_probability` and
        each node has a ``dict`` payload with the key ``is_boundary`` and the value is
        a boolean.
        Returns
        -------
        retworkx.PyGraph
            retworkx graph corresponding to the matching graph
        """
        G = rx.PyGraph(multigraph=False)
        G.add_nodes_from([{} for _ in range(self.num_nodes)])
        G.extend_from_weighted_edge_list(self.edges())
        boundary = self.boundary
        for i in G.node_indices():
            is_boundary = i in boundary
            G[i]['is_boundary'] = is_boundary
        return G

    def set_boundary_nodes(self, nodes: Set[int]) -> None:
        """
        Set boundary nodes in the matching graph. This defines the
        nodes in `nodes` to be boundary nodes.
        Parameters
        ----------
        nodes: set[int]
            The IDs of the nodes to be set as boundary nodes
        Examples
        --------
        >>> import pymatching
        >>> m = pymatching.Matching()
        >>> m.add_edge(0, 1)
        >>> m.add_edge(1, 2)
        >>> m.set_boundary_nodes({0, 2})
        >>> m.boundary
        {0, 2}
        >>> m
        <pymatching.Matching object with 1 detector, 2 boundary nodes, and 2 edges>
        """
        self._matching_graph.set_boundary(nodes)

    def set_min_num_fault_ids(self, min_num_fault_ids: int) -> None:
        """
        Set the minimum number of fault ids in the matching graph.

        Let `max_id` be the maximum fault id assigned to any of the edges in the graph. Then setting
        `min_num_fault_ids` will ensure that `Matching.num_fault_ids=max(min_num_fault_ids, max_id)`.
        Note that `Matching.num_fault_ids` sets the length of the correction array output by `Matching.decode`.
        Parameters
        ----------
        min_num_fault_ids: int
            The required minimum number of fault ids in the matching graph

        """
        self._matching_graph.set_min_num_observables(min_num_fault_ids)

    @property
    def num_fault_ids(self) -> int:
        """
        The number of fault IDs defined in the matching graph
        Returns
        -------
        int
            Number of fault IDs
        """
        return self._matching_graph.get_num_observables()

    @property
    def boundary(self) -> Set[int]:
        """Return the indices of the boundary nodes.
        Note that this property is a copy of the set of boundary nodes.
        In-place modification of the set Matching.boundary will not
        change the boundary nodes of the matching graph - boundary nodes should
        instead be set or updated using the `Matching.set_boundary_nodes` method.
        Returns
        -------
        set of int
            The indices of the boundary nodes
        """
        return self._matching_graph.get_boundary()

    @property
    def num_nodes(self) -> int:
        """
        The number of nodes in the matching graph
        Returns
        -------
        int
            The number of nodes
        """
        return self._matching_graph.get_num_nodes()

    @property
    def num_edges(self) -> int:
        """
        The number of edges in the matching graph
        Returns
        -------
        int
            The number of edges
        """
        return self._matching_graph.get_num_edges()

    @property
    def num_detectors(self) -> int:
        """
        The number of detectors in the matching graph. A
        detector is a node that can have a non-trivial syndrome
        (i.e. it is a node that is not a boundary node).
        Returns
        -------
        int
            The number of detectors
        """
        return self._matching_graph.get_num_detectors()
