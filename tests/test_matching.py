import os

import pytest
import numpy as np
from scipy.sparse import csc_matrix, load_npz, csr_matrix
import pytest
import networkx as nx

from pymatching._cpp_mwpm import WeightedStabiliserGraph
from pymatching import Matching

TEST_DIR = dir_path = os.path.dirname(os.path.realpath(__file__))


def test_mwpm_decode_method():
    fn = "css_2D-toric_(4,4)_[[18,2,3]]_Hx.npz"
    H = load_npz(os.path.join(TEST_DIR, 'data', fn))
    m = Matching(H)
    n = np.zeros(H.shape[1], dtype=int)
    n[5] = 1
    n[10] = 1
    z = H.dot(n) % 2
    c = m.decode(z)
    assert(np.array_equal(c,n))


noisy_fixtures = [
    (
        np.array([
            [0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
        ]),
        np.array([
            [0,0,0,0,0,0,0,1,0],
            [0,0,0,0,0,0,1,0,0],
            [0,0,0,0,0,0,0,0,0]
        ]).T,
        np.array([0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0])    
    ),
    (
        np.array([
            [0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
        ]),
        np.array([
            [0,0,0,0,0,1,0,0,0],
            [0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0]
        ]).T,
        np.array([0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0])
    )
]

@pytest.mark.parametrize("n,z_err,c_expected", noisy_fixtures)
def test_mwpm_noisy_decode(n, z_err, c_expected):
    fn = "css_2D-toric_(4,4)_[[18,2,3]]_Hx.npz"
    H = load_npz(os.path.join(TEST_DIR, 'data', fn))
    m = Matching(H, repetitions=z_err.shape[1])
    n_all = np.cumsum(n, 0) % 2
    z_noiseless = H.dot(n_all.T) % 2
    z_noisy = (z_noiseless + z_err) % 2
    z_noisy[:,1:] = (z_noisy[:,1:] - z_noisy[:,:-1]) % 2
    c = m.decode(z_noisy)
    assert(np.array_equal(c, c_expected))


def test_bad_qubit_id_raises_value_error():
    g = nx.Graph()
    g.add_edge(0,1, qubit_id='test')
    with pytest.raises(ValueError):
        m = Matching(g)
    g = nx.Graph()
    g.add_edge(0,1, qubit_id=[[1],[2]])
    with pytest.raises(ValueError):
        m = Matching(g)


def test_precompute_shortest_paths():
    g = nx.Graph()
    g.add_edge(0, 1, qubit_id=0)
    g.add_edge(1, 2, qubit_id=1)
    m = Matching(g)
    assert not m.stabiliser_graph.has_computed_all_pairs_shortest_paths()
    m2 = Matching(g, precompute_shortest_paths=True)
    assert m2.stabiliser_graph.has_computed_all_pairs_shortest_paths()


def test_decode_all_neighbours():
    g = nx.Graph()
    g.add_edge(0, 1, qubit_id=0)
    g.add_edge(1, 2, qubit_id=1)
    m = Matching(g)
    noise = m.decode([1,0,1], num_neighbours=None)
    assert np.array_equal(noise, np.array([1,1]))


def test_bad_syndrome_raises_value_error():
    g = nx.Graph()
    g.add_edge(0, 1, qubit_id=0)
    g.add_edge(1, 2, qubit_id=1)
    m = Matching(g)
    with pytest.raises(ValueError):
        noise = m.decode('test')


distance_fixtures = [
    (2,11,1),
    (3,13,2),
    (2,8,1),
    (2,98, 11)
]


@pytest.mark.parametrize("node1,node2,expected", distance_fixtures)
def test_spacetime_distance(node1, node2, expected):
    fn = "css_2D-toric_(4,4)_[[18,2,3]]_Hx.npz"
    H = load_npz(os.path.join(TEST_DIR, 'data', fn))
    m = Matching(H)
    d = m.stabiliser_graph.space_time_distance(node1, node2)
    assert(d == expected)


spacetime_path_fixtures = [
    (1,184,[1,4]),
    (2,62,[2,8])
]


@pytest.mark.parametrize("node1,node2,expected", spacetime_path_fixtures)
def test_spacetime_shortest_path(node1, node2, expected):
    fn = "css_2D-toric_(4,4)_[[18,2,3]]_Hx.npz"
    H = load_npz(os.path.join(TEST_DIR, 'data', fn))
    m = Matching(H)
    path = m.stabiliser_graph.space_time_shortest_path(node1, node2)
    assert(path == expected)


def test_boundary_from_check_matrix():
    H = csr_matrix(np.array([[1,1,0,0,0],[0,1,1,0,0],
                             [0,0,1,1,0],[0,0,0,1,1]]))
    m = Matching(H)
    assert m.boundary == [4]
    assert np.array_equal(m.decode(np.array([1,0,0,0])), np.array([1,0,0,0,0]))
    assert np.array_equal(m.decode(np.array([0,1,0,0])), np.array([1,1,0,0,0]))
    assert np.array_equal(m.decode(np.array([0,1,1,0])), np.array([0,0,1,0,0]))
    assert np.array_equal(m.decode(np.array([0,0,1,0])), np.array([0,0,0,1,1]))


def test_boundary_from_networkx():
    g = nx.Graph()
    g.add_edge(4,0, qubit_id=0)
    g.add_edge(0,1, qubit_id=1)
    g.add_edge(1,2, qubit_id=2)
    g.add_edge(2,3, qubit_id=3)
    g.add_edge(3,4, qubit_id=4)
    g.nodes()[4]['is_boundary'] = True
    m = Matching(g)
    assert m.boundary == [4]
    assert np.array_equal(m.decode(np.array([1,0,0,0])), np.array([1,0,0,0,0]))
    assert np.array_equal(m.decode(np.array([0,1,0,0])), np.array([1,1,0,0,0]))
    assert np.array_equal(m.decode(np.array([0,1,1,0])), np.array([0,0,1,0,0]))
    assert np.array_equal(m.decode(np.array([0,0,1,0])), np.array([0,0,0,1,1]))


def test_boundaries_from_networkx():
    g = nx.Graph()
    g.add_edge(0,1, qubit_id=0)
    g.add_edge(1,2, qubit_id=1)
    g.add_edge(2,3, qubit_id=2)
    g.add_edge(3,4, qubit_id=3)
    g.add_edge(4,5, qubit_id=4)
    g.add_edge(0,5, qubit_id=-1, weight=0.0)
    g.nodes()[0]['is_boundary'] = True
    g.nodes()[5]['is_boundary'] = True
    m = Matching(g)
    assert m.boundary == [0,5]
    assert np.array_equal(m.decode(np.array([0,1,0,0,0,0])), np.array([1,0,0,0,0]))
    assert np.array_equal(m.decode(np.array([0,0,1,0,0])), np.array([1,1,0,0,0]))
    assert np.array_equal(m.decode(np.array([0,0,1,1,0])), np.array([0,0,1,0,0]))
    assert np.array_equal(m.decode(np.array([0,0,0,1,0])), np.array([0,0,0,1,1]))


def test_nonzero_matrix_elements_not_one_raises_value_error():
    H = csr_matrix(np.array([[0,1.01,1.01],[1.01,1.01,0]]))
    with pytest.raises(ValueError):
        Matching(H)


def test_too_many_checks_per_qubit_raises_value_error():
    H = csr_matrix(np.array([[1,1,0,0],[1,0,1,0],[1,0,0,1]]))
    with pytest.raises(ValueError):
        Matching(H)


def test_negative_weight_raises_value_error():
    g = nx.Graph()
    g.add_edge(0,1,weight=-1)
    with pytest.raises(ValueError):
        Matching(g)
    with pytest.raises(ValueError):
        Matching(csr_matrix([[1,1,0],[0,1,1]]), spacelike_weights=np.array([1,1,-1]))


def test_odd_3d_syndrome_raises_value_error():
    H = csr_matrix(np.array([[1,1,0],[0,1,1]]))
    m = Matching(H)
    with pytest.raises(ValueError):
        m.decode(np.array([[1,0],[0,0]]))


def test_add_noise_to_unweighted_returns_none():
    m = Matching(csr_matrix(np.array([[1,1,0],[0,1,1]])))
    assert m.add_noise() == None
    m = Matching(csr_matrix(np.array([[1,1,0],[0,1,1]])), 
             error_probabilities=np.array([0.5,0.7,-0.1]))
    assert m.add_noise() == None


def test_error_probability_from_array():
    H = csr_matrix(np.array([[1,1,0,0,0],[0,1,1,0,0],
                             [0,0,1,1,0],[0,0,0,1,1]]))
    m = Matching(H, error_probabilities=np.array([0.,0.,0.,0.,1.]))
    assert np.array_equal(m.add_noise()[0], np.array([0,0,0,0,1]))
    assert np.array_equal(m.add_noise()[1], np.array([0,0,0,1,1]))
    m = Matching(H, error_probabilities=np.array([0.,0.,0.,0.,0.]))
    assert np.array_equal(m.add_noise()[0], np.array([0,0,0,0,0]))
    assert np.array_equal(m.add_noise()[1], np.array([0,0,0,0,0]))
    m = Matching(H, error_probabilities=0.0)
    assert np.array_equal(m.add_noise()[0], np.array([0,0,0,0,0]))
    assert np.array_equal(m.add_noise()[1], np.array([0,0,0,0,0]))
    m = Matching(H, error_probabilities=1.0)
    assert np.array_equal(m.add_noise()[0], np.array([1,1,1,1,1]))
    assert np.array_equal(m.add_noise()[1], np.array([0,0,0,0,0]))


def test_weighted_mwpm_from_array():
    H = csc_matrix([[1,0],[1,1],[0,1]])
    m = Matching(H, spacelike_weights=np.array([1., 2.]))
    assert m.stabiliser_graph.distance(0, 1) == 1.
    assert m.stabiliser_graph.distance(1, 2) == 2.
    with pytest.raises(ValueError):
        m = Matching(H, spacelike_weights=np.array([1.]))
    with pytest.raises(ValueError):
        m = Matching(H, spacelike_weights=np.array([1., -2.]))


def test_unweighted_stabiliser_graph_from_networkx():
    w = nx.Graph()
    w.add_edge(0, 1, qubit_id=0, weight=7.0)
    w.add_edge(0, 5, qubit_id=1, weight=14.0)
    w.add_edge(0, 2, qubit_id=2, weight=9.0)
    w.add_edge(1, 2, qubit_id=-1, weight=10.0)
    w.add_edge(1, 3, qubit_id=3, weight=15.0)
    w.add_edge(2, 5, qubit_id=4, weight=2.0)
    w.add_edge(2, 3, qubit_id=-1, weight=11.0)
    w.add_edge(3, 4, qubit_id=5, weight=6.0)
    w.add_edge(4, 5, qubit_id=6, weight=9.0)
    m = Matching(w)
    assert(m.num_qubits == 7)
    assert(m.num_stabilisers == 6)
    assert(m.stabiliser_graph.shortest_path(3, 5) == [3, 2, 5])
    assert(m.stabiliser_graph.distance(5, 0) == pytest.approx(11.0))
    assert(np.array_equal(
        m.decode(np.array([1,0,1,0,0,0])),
        np.array([0,0,1,0,0,0,0]))
    )
    with pytest.raises(ValueError):
        m.decode(np.array([1,1,0]))
    with pytest.raises(ValueError):
        m.decode(np.array([1,1,1,0,0,0]))
    assert(np.array_equal(
        m.decode(np.array([1,0,0,0,0,1])),
        np.array([0,0,1,0,1,0,0]))
    )
    assert(np.array_equal(
        m.decode(np.array([0,1,0,0,0,1])),
        np.array([0,0,0,0,1,0,0]))
    )


def test_mwmpm_from_networkx():
    g = nx.Graph()
    g.add_edge(0, 1, qubit_id=0)
    g.add_edge(0, 2, qubit_id=1)
    g.add_edge(1, 2, qubit_id=2)
    m = Matching(g)
    assert(isinstance(m.stabiliser_graph, WeightedStabiliserGraph))
    assert(m.num_stabilisers == 3)
    assert(m.num_qubits == 3)
    assert(m.stabiliser_graph.distance(0,2) == 1)
    assert(m.stabiliser_graph.shortest_path(0,2) == [0,2])

    g = nx.Graph()
    g.add_edge(0, 1)
    g.add_edge(0, 2)
    g.add_edge(1, 2)
    m = Matching(g)
    assert(isinstance(m.stabiliser_graph, WeightedStabiliserGraph))
    assert(m.num_stabilisers == 3)
    assert(m.num_qubits == 0)
    assert(m.stabiliser_graph.distance(0,2) == 1)
    assert(m.stabiliser_graph.shortest_path(0,2) == [0,2])

    g = nx.Graph()
    g.add_edge(0, 1, weight=1.5)
    g.add_edge(0, 2, weight=1.7)
    g.add_edge(1, 2, weight=1.2)
    m = Matching(g)
    assert(isinstance(m.stabiliser_graph, WeightedStabiliserGraph))
    assert(m.num_stabilisers == 3)
    assert(m.num_qubits == 0)
    assert(m.stabiliser_graph.distance(0,2) == pytest.approx(1.7))
    assert(m.stabiliser_graph.shortest_path(0,2) == [0,2])


def test_double_weight_matching():
    w = nx.Graph()
    w.add_edge(0, 1, qubit_id=0, weight=0.97)
    w.add_edge(2, 3, qubit_id=1, weight=1.98)
    w.add_edge(0, 2, qubit_id=2, weight=1.1)
    w.add_edge(1, 3, qubit_id=3, weight=1.2)
    m = Matching(w)
    assert(
        list(m.decode(np.array([1,1,1,1]))) == list(np.array([0,0,1,1]))
        )


def test_repr():
    g = nx.Graph()
    g.add_edge(0, 1, qubit_id=0)
    g.add_edge(1, 2, qubit_id=1)
    g.add_edge(2, 3, qubit_id=2)
    g.nodes[0]['is_boundary'] = True
    g.nodes[3]['is_boundary'] = True
    g.add_edge(0, 3, weight=0.0)
    m = Matching(g)
    assert m.__repr__() == ("<pymatching.Matching object with 3 qubits, "
                            "2 stabilisers, 2 boundary nodes, and 4 edges>")


def test_wrong_connected_components_raises_value_error():
    g = nx.Graph()
    g.add_edge(0, 1, qubit_id=0)
    g.add_edge(1, 2, qubit_id=1)
    g.add_edge(2, 0, qubit_id=2)
    g.add_edge(3, 4, qubit_id=3)
    g.add_edge(4, 5, qubit_id=4)
    g.add_edge(5, 3, qubit_id=5)
    with pytest.raises(ValueError):
        Matching(g)
    g = nx.Graph()
    g.add_edge(0, 1, qubit_id=0)
    g.add_edge(1, 2, qubit_id=1)
    g.add_edge(2, 0, qubit_id=2)
    m = Matching(g)
    assert m.stabiliser_graph.get_num_connected_components() == 1


def test_small_num_neighbours_raises_value_error():
    m = Matching(np.array([
        [1,1,0,0],
        [0,1,1,0],
        [0,0,1,1]
    ]))
    min_num_neighbours = 10
    for i in range(min_num_neighbours):
        with pytest.raises(ValueError):
            m.decode([0,1,1], num_neighbours=i)
    for i in range(min_num_neighbours, 2*min_num_neighbours):
        m.decode([0,1,1], num_neighbours=i)


def test_high_qubit_id_raises_value_error():
    g = nx.Graph()
    g.add_edge(0,1,qubit_id=1)
    with pytest.raises(ValueError):
        Matching(g)


def test_high_node_id_raises_value_error():
    g = nx.Graph()
    g.add_edge(1, 2)
    with pytest.raises(ValueError):
        Matching(g)
