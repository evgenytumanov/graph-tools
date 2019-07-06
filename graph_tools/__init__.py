#!/usr/bin/env python3
#
# Tools for graph theory and complex networks written in Python
# Copyright (c) 2018, Hiroyuki Ohsaki.
# All rights reserved.
#
# $Id: graphtools.py,v 1.33 2019/07/05 17:34:20 ohsaki Exp $
#

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

# Contributors
# Ryo Nakamura <r-nakamura[atmark]kwansei.ac.jp>
# Yuichi Yasuda <yuichi[atmark]kwansei.ac.jp>

from collections import defaultdict, deque, OrderedDict
import itertools
import functools
import math
import random
import re
import time

from perlcompat import warn, die
import tbdump
import numpy
import pytess

CREATE_SUBP = {
    'random': 'create_random_graph',
    'random_sparse': 'create_random_sparse_graph',
    'barabasi': 'create_barabasi_graph',
    'ba': 'create_barabasi_graph',
    'barandom': 'create_barabasi_random_graph',
    'general_ba': 'create_generalized_barabasi_graph',
    'ring': 'create_ring_graph',
    'tree': 'create_tree_graph',
    'btree': 'create_btree_graph',
    'latent': 'create_latent_graph',
    'treeba': 'create_treeba_graph',
    'lattice': 'create_lattice_graph',
    'voronoi': 'create_voronoi_graph',
    'db': 'create_degree_bounded_graph',
    'degree_bounded': 'create_degree_bounded_graph',
    'configuration': 'create_configuration_graph',
    'li_maini': 'create_li_maini_graph',
}
CREATE_TYPES = sorted(CREATE_SUBP.keys())

IMPORT_SUBP = {
    'dot': 'import_dot',
    'dimacs': 'import_dimacs',
    'inet': 'import_inet',
    'brite': 'import_brite',
    'gw': 'import_gw',
    'nsnode': 'import_nsnode',
    'nsagent': 'import_nsagent',
    'metis': 'import_metis',
    'edge': 'import_edge',
    'cell': 'import_cell',
}
IMPORT_FORMATS = sorted(IMPORT_SUBP.keys())

EXPORT_SUBP = {
    'dot': 'export_dot',
    'dimacs': 'export_dimacs',
    'inet': 'export_inet',
    'nsnode': 'export_nsnode',
    'nsagent': 'export_nsagent',
    'nsagent_edge': 'export_nsagent_edge',
    'nsagent_udp': 'export_nsagent_udp',
    'metis': 'export_metis',
    'pdnsnode': 'export_pdnsnode',
    'pdnsagent': 'export_pdnsagent',
    'gdl': 'export_gdl',
    'cell': 'export_cell',
}
EXPORT_FORMATS = sorted(EXPORT_SUBP.keys())

MAX_RETRIES = 100

METIS_EDGE_WEIGHT_MASK = 1
METIS_VERTEX_WEIGHT_MASK = 2

PDNS_NETMASK = '255.255.255.0'
PDNS_AGENT_PORT = 1234

def str2number(v):
    # FIXME: shoud not check type
    if type(v) != str:
        return v
    # remove preceeding/trailing spaces
    v = v.strip()
    if v.startswith('0x'):
        return int(v, 16)
    elif re.match(r'[\d+-]+$', v):
        return int(v)
    elif re.match(r'[\d.eE+-]+$', v):
        return float(v)
    else:
        return v

class Graph:
    def __init__(self, directed=True, multiedged=True):
        self.G = {}  # graph
        self.V = {}  # vertices
        self.EI = {}  # incoing edges
        self.EO = {}  # outgoin edges
        self.T = {}  # shortest path cache (total distances from vertex)
        self.P = {}  # shortest path cache (preceeding vertices list)
        self.Cb = {}  # betweenness centrality cache
        self._directed = directed

    def __repr__(self):
        return self.export_dot()

    def directed(self):
        return self._directed

    def undirected(self):
        return not self._directed

    def multiedged(self):
        return True

    def set_graph_attribute(self, attr, val):
        self.G[attr] = val

    def get_graph_attribute(self, attr):
        return self.G.get(attr, None)

    def average_degree(self):
        total, count = 0, 0
        for v in self.vertices():
            total += self.degree(v)
            count += 1
        return total / count

    def expect_undirected(self):
        if not self.undirected():
            die('undirected graph expected')

    def expect_directed(self):
        if not self.directed():
            die('directed graph expected')

    def expect_multiedged(self):
        if not self.multiedged():
            die('multiedged graph expected')

    # vertex ----------------------------------------------------------------
    def vertices(self):
        return list(self.V.keys())

    def has_vertex(self, v):
        if self.V.get(v, None) is None:
            return False
        else:
            return True

    def add_vertex(self, v):
        if not self.has_vertex(v):
            self.V[v] = {}  # default vertex attribute

    def add_vertices(self, *vertices):
        for v in vertices:
            self.add_vertex(v)

    def predecessors(self, v, ignore=False):
        if not ignore:
            self.expect_directed()
        if not self.EI.get(v, None):
            return []
        return list(self.EI[v].keys())

    def successors(self, u, ignore=False):
        if not ignore:
            self.expect_directed()
        if not self.EO.get(u, None):
            return []
        return list(self.EO[u].keys())

    def neighbors(self, v):
        found = set()
        for u in self.predecessors(v, ignore=True):
            found.add(u)
        for u in self.successors(v, ignore=True):
            found.add(u)
        return list(found)

    def set_vertex_attribute(self, v, attr, val):
        if not self.has_vertex(v):
            self.add_vertex(v)
        self.V[v][attr] = val

    def get_vertex_attribute(self, v, attr):
        return self.V[v].get(attr, None)

    def set_vertex_attributes(self, v, adict):
        for key, val in adict.items():
            self.V[v][key] = val

    def get_vertex_attributes(self, v):
        return self.V.get(v, {})

    def set_vertex_weight(self, v, val):
        return self.set_vertex_attribute(v, 'weight', val)

    def get_vertex_weight(self, v):
        return self.get_vertex_attribute(v, 'weight')

    def delete_vertex(self, v):
        if not self.has_vertex(v):
            return None
        for u in self.neighbors(v):
            try:
                del self.EO[u][v]
            except KeyError:
                pass
            try:
                del self.EI[u][v]
            except KeyError:
                pass
        del self.V[v]
        try:
            del self.EO[v]
        except KeyError:
            pass
        try:
            del self.EI[v]
        except KeyError:
            pass

    def delete_vertices(self, alist):
        for v in alist:
            self.delete_vertex(v)

    def random_vertex(self):
        return random.choice(self.vertices())

    # edge ----------------------------------------------------------------
    def edges(self):
        found = []
        for u in self.EO:
            for v in self.EO[u]:
                for id in self.get_multiedge_ids(u, v):
                    found.append([u, v])
        return found

    def unique_edges(self):
        found = []
        for u in self.EO:
            for v in self.EO[u]:
                found.append([u, v])
        return found

    def has_edge(self, u, v):
        if self.undirected() and u > v:
            u, v = v, u
        if not self.EO.get(u, None):
            return False
        if not self.EO[u].get(v, None):
            return False
        return True

    # return the continue edge ID, which is equivalent to the number of
    # multi-edges between vertices
    def get_multiedge_ids(self, u, v):
        if self.undirected() and u > v:
            u, v = v, u
        if not self.has_edge(u, v):
            return []
        return list(self.EO[u][v].keys())

    def get_edge_count(self, u, v):
        ids = self.get_multiedge_ids(u, v)
        if ids:
            return len(ids)
        else:
            return 0

    def add_edge(self, u, v):
        if self.undirected() and u > v:
            u, v = v, u
        count = self.get_edge_count(u, v)
        self.add_vertices(u, v)
        if not self.EO.get(u, None):
            self.EO[u] = {}
        if not self.EO[u].get(v, None):
            self.EO[u][v] = {}
        self.EO[u][v][count] = {}  # default vertex attribute
        if not self.EI.get(v, None):
            self.EI[v] = {}
        if not self.EI[v].get(u, None):
            self.EI[v][u] = {}
        self.EI[v][u][count] = {}  # default vertex attribute
        return count

    def delete_edge(self, u, v):
        if self.undirected() and u > v:
            u, v = v, u
        if not self.has_edge(u, v):
            return None
        count = self.get_edge_count(u, v) - 1
        del self.EO[u][v][count]
        del self.EI[v][u][count]
        if (count == 0):
            del self.EO[u][v]
            del self.EI[v][u]
        return count

    def edges_from(self, u, ignore=False):
        if not ignore:
            self.expect_directed()
        found = []
        for v in self.successors(u, ignore):
            for count in self.get_multiedge_ids(u, v):
                found.append([u, v])
        return found

    def edges_to(self, v, ignore=False):
        if not ignore:
            self.expect_directed()
        found = []
        for u in self.predecessors(v, ignore):
            for count in self.EI[v][u]:
                found.append([u, v])
        return found

    def edges_at(self, v):
        found = []
        found.extend(self.edges_from(v, ignore=True))
        found.extend(self.edges_to(v, ignore=True))
        return found

    def out_degree(self, u, ignore=False):
        if not ignore:
            self.expect_directed()
        return len(self.edges_from(u))

    def in_degree(self, v, ignore=False):
        if not ignore:
            self.expect_directed()
        return len(self.edges_to(v))

    def degree(self, v):
        if self.undirected():
            return len(self.edges_at(v))
        else:
            return self.in_degree(v) + self.out_degree(v)

    vertex_degree = degree

    def random_edge(self):
        return random.choice(self.edges())

    def set_edge_attribute_by_id(self, u, v, id, attr, val):
        if not attr:
            warn('set_edge_attribute_by_id: no attribute specified.')

        if self.undirected() and u > v:
            u, v = v, u
        self.EO[u][v].setdefault(id, {})
        self.EO[u][v][id][attr] = val

    def get_edge_attribute_by_id(self, u, v, id, attr):
        if not attr:
            warn('get_edge_attribute_by_id: no attribute specified.')
        if self.undirected() and u > v:
            u, v = v, u
        return self.EO[u][v][id].get(attr, None)

    def set_edge_attributes_by_id(self, u, v, id, adict):
        if self.undirected() and u > v:
            u, v = v, u
        for key, val in adict.items():
            self.EO[u][v][id][key] = val

    def get_edge_attributes_by_id(self, u, v, id):
        if self.undirected() and u > v:
            u, v = v, u
        return self.EO[u][v][id]

    def set_edge_weight_by_id(self, u, v, id, val):
        return self.set_edge_attribute_by_id(u, v, id, 'weight', val)

    def get_edge_weight_by_id(self, u, v, id):
        return self.get_edge_attribute_by_id(u, v, id, 'weight')

    def set_edge_weight(self, u, v, w):
        return self.set_edge_attribute_by_id(u, v, 0, 'weight', w)

    def get_edge_weight(self, u, v):
        return self.get_edge_attribute_by_id(u, v, 0, 'weight')

    # algorithm ----------------------------------------------------------------
    def dijkstra(self, s):
        self.expect_directed()
        dist = {}
        prev = {}
        for v in self.vertices():
            prev[v] = []
        dist[s] = 0

        S = []
        Q = self.vertices()
        INFINITY = 2 << 30
        while Q:
            Q = sorted(Q, key=lambda x: dist.get(x, INFINITY))
            u = Q.pop(0)
            if dist.get(u, None) is None:
                break
            S.append(u)
            for v in self.successors(u):
                # FIXME: must reject multi-edged graph
                w = self.get_edge_weight_by_id(u, v, 0) or 1
                if dist.get(v, None) is None or dist[v] > (
                        dist.get(u, INFINITY) + w):
                    dist[v] = dist[u] + w
                    prev[v] = [u]
                elif dist[v] == (dist.get(u, INFINITY) +
                                 w):  # handle equal paths
                    prev[v].append(u)
        self.T[s] = dist
        self.P[s] = prev
        return dist, prev

    def shortest_paths(self, s, t):
        """Return the all shortest-paths from vertex S to vertex T."""

        def find_path(s, t):
            # P[s] stores the shortest-path tree from vertex S.
            # P{s][t] is a set of previous nodes in the shortest-path tree.
            for prev in self.P[s][t]:
                if prev == s:
                    yield [s, t]
                else:
                    for path in find_path(s, prev):
                        yield path + [t]

        self.expect_directed()
        # build shortest-path tree if not cached yet
        if not s in self.P:
            self.dijkstra(s)
        return list(find_path(s, t))

    def dijkstra_all_pairs(self):
        for v in self.vertices():
            self.dijkstra(v)

    def floyd_warshall(self):
        self.expect_directed()
        # initialize weight matrix
        # NOTE: works well for sparse graphs
        path = {}
        next = {}
        for v in self.vertices():
            path[v] = {}
            next[v] = {}

        for e in self.edges():
            path[e[0]][e[1]] = self.get_edge_weight_by_id(*e, 0) or 1

        # run Floyd-Warshall algorithm to find all-pairs shortest paths
        # NOTE: Floyd-Warshall is good for _ in DENSE graphs:
        INFINITY = 10**10
        for k in self.vertices():
            for u in self.vertices():
                for v in self.vertices():
                    if path[u].get(k, INFINITY) + path[k].get(v, INFINITY) \
                        < path[u].get(v, INFINITY):
                        path[u][v] = path[u][k] + path[k][v]
                        next[u][v] = k
        self.T = path

    def is_reachable(self, u, v):
        if not self.T.get(u, None):
            self.dijkstra(u)
        return self.T[u].get(v, None)

    def is_connected(self):
        v = self.random_vertex()
        explored = self.explore(v)
        return len(explored) == len(self.vertices())

    def explore(self, s):
        explored = set()
        need_visit = set()
        need_visit.add(s)
        while need_visit:
            u = need_visit.pop()
            explored.add(u)
            for v in self.neighbors(u):
                if v not in explored:
                    need_visit.add(v)
        return explored

    # return all components (i.e., connected subgraphs)
    def components(self):
        components = []
        # record unvisisted vertices
        unvisited = set(self.vertices())
        while unvisited:
            # start exploration from one of unvisited vertices
            v = unvisited.pop()
            explored = self.explore(v)
            components.append(explored)
            # remove all visisted vertices
            unvisited -= explored
        # return components in descending order (?)
        return components

    def maximal_component(self):
        components = sorted(self.components(), key=lambda x: len(x))
        return components[-1]

    def betweenness(self, v):
        """Return the betweenness centrality for vertex v.  This program
        implements Algorithm 1 (betweenness centrality in unweighted graphs)
        in U. Brandes, `A Fast Algorithm for Betweeness Centrality,' Journal
        of Mathematical Sociology, 2001."""

        def _update_betweenness():
            self.expect_undirected()

            # check if the graph is unweighted
            for _ in range(10):  # test 10 sample edges
                u, v = self.random_edge()
                w = self.get_edge_weight(u, v)
                if w is not None and w != 1:
                    die(f'Only supports unweighted graphs.')

            # betweenness centrality for vertices
            self.Cb = {v: 0 for v in self.vertices()}

            for s in self.vertices():
                S = []  # empty stack
                P = {w: [] for w in self.vertices()}
                sigma = {t: 0 for t in self.vertices()}
                sigma[s] = 1
                d = {t: -1 for t in self.vertices()}
                d[s] = 1
                Q = deque()  # empty queue
                Q.append(s)

                while Q:
                    v = Q.popleft()
                    S.append(v)
                    for w in self.neighbors(v):
                        # found for the first time?
                        if d[w] < 0:
                            Q.append(w)
                            d[w] = d[v] + 1
                        # shortest path to w via v?
                        if d[w] == d[v] + 1:
                            sigma[w] += sigma[v]
                            P[w].append(v)

                delta = {v: 0 for v in self.vertices()}
                # S returns vertices in order of non-increasing distance from s
                while S:
                    w = S.pop()
                    for v in P[w]:
                        delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
                    if w != s:
                        self.Cb[w] += delta[w]

        if not v in self.Cb:
            _update_betweenness()
        return self.Cb[v]

    # graph ----------------------------------------------------------------
    def copy_graph(self):
        T = Graph(directed=self.directed(), multiedged=self.multiedged())
        for v in self.vertices():
            T.add_vertex(v)
            T.set_vertex_attributes(v, self.get_vertex_attributes(v))

        for e in self.edges():
            T.add_edge(*e)
            for id in self.get_multiedge_ids(*e):
                T.set_edge_attributes_by_id(*e, id, \
                    self.get_edge_attributes_by_id(*e, id))
        return T

    def directed_copy(self):
        T = Graph(directed=True, multiedged=self.multiedged())
        for v in self.vertices():
            T.add_vertex(v)

        for e in self.edges():
            T.add_edge(*e)
            if self.undirected():
                T.add_edge(e[1], e[0])

        return T

    def complete_graph(self):
        for u in self.vertices():
            for v in self.vertices():
                if u >= v:
                    continue
                if not self.has_edge(u, v):
                    self.add_edge(u, v)
        return self

    def adjacency_matrix(self):
        """Return the adjacency matrix of graph as NumPy.ndarray object."""
        N = len(self.vertices())
        m = numpy.zeros((N, N), int)
        for u, v in self.edges():
            m[u - 1, v - 1] += 1
            if self.undirected():
                m[v - 1, u - 1] += 1
        return m

    def diagonal_matrix(self):
        N = len(self.vertices())
        m = numpy.zeros((N, N), int)
        for v in self.vertices():
            m[v - 1, v - 1] = self.degree(v)
        return m

    def laplacian_matrix(self):
        return self.diagonal_matrix() - self.adjacency_matrix()

    def adjacency_matrix_eigvals(self):
        return sorted(numpy.linalg.eigvals(self.adjacency_matrix()))

    def laplacian_matrix_eigvals(self):
        return sorted(numpy.linalg.eigvals(self.laplacian_matrix()))

    def spectral_radius(self):
        lmbda = self.adjacency_matrix_eigvals()
        return lmbda[-1]

    def spectral_gap(self):
        lmbda = self.adjacency_matrix_eigvals()
        return lmbda[-1] - lmbda[-2]

    def natural_connectivity(self):
        N = len(self.vertices())
        lmbda = self.adjacency_matrix_eigvals()
        return math.log(sum(numpy.exp(lmbda)) / N)

    def algebraic_connectivity(self):
        mu = self.laplacian_matrix_eigvals()
        return mu[1]

    def effective_resistance(self):
        N = len(self.vertices())
        mu = self.laplacian_matrix_eigvals()
        print(mu)
        return N * sum([1 / (mu + 1e-100) for mu in mu[1:]])

    def spanning_tree_count(self):
        N = len(self.vertices())
        mu = self.laplacian_matrix_eigvals()
        return functools.reduce(lambda x, y: x * y,
                                [1 / (mu + 1e-100) for mu in mu[1:]]) / N

    # util ----------------------------------------------------------------
    def header_string(self, comment='# '):
        date = time.strftime('%Y/%M/%D %H:%M:%S', time.localtime())
        type = 'directed' if self.is_directed() else 'undirected'
        vcount = len(self.vertices())
        ecount = len(self.edges())
        astr = f"""{comment}Generated by graphtools (version 1.0) at {date}
{comment}{type}, {vcount} vertices, {ecount} edges
"""
        return astr

    # create ----------------------------------------------------------------
    def create_graph(self, atype, *args):
        name = CREATE_SUBP.get(atype, None)
        if not name:
            warn(f"No graph creation support for type `{type}'")
            return None
        method = getattr(self, name, None)
        if not method:
            warn(f"Graph creation method `{name}' not found")
            return None
        return method(*args)

    def create_random_graph(self, N=10, E=20, no_multiedge=False):
        if E < N:
            die('Too small number of edges')

        for v in range(1, N + 1):
            self.add_vertex(v)

        # add first (N - 1) edges for making sure connectivity
        for i in range(1, N):
            u = i + 1
            v = random.randrange(1, u)
            if random.uniform(0, 1) >= 0.5:
                self.add_edge(u, v)
            else:
                self.add_edge(v, u)

        # randomly add remaining (E - (N - 1)) edges
        for i in range(1, E - (N - 1) + 1):
            # FIXME: avoid cycle edges, but this may take log time
            ntries = 1
            while ntries < MAX_RETRIES:
                u = random.randrange(1, N + 1)
                v = random.randrange(1, N + 1)
                if not no_multiedge and u != v:
                    break
                if no_multiedge and u != v and not self.has_edge(u, v):
                    break
            self.add_edge(u, v)
        return self

    def create_erdos_renyi_graph(self, N=100, p=.04):
        self.expect_undirected()
        self.add_vertices(*range(1, N + 1))
        for u, v in itertools.combinations(self.vertices(), 2):
            if random.random() < p:
                self.add_edge(u, v)
        return self

    def create_random_sparse_graph(self, N=10, E=20, no_multiedge=False):
        for i in range(1, N + 1):
            self.add_vertex(i)

        # randomly add remaining Eedges
        for i in range(1, E + 1):
            # FIXME: avoid cycle edges, but this may take log time
            ntries = 1
            while ntries < MAX_RETRIES:
                u = random.randrange(1, N + 1)
                v = random.randrange(1, N + 1)
                if not no_multiedge and u != v:
                    break
                if no_multiedge and u != v and not self.has_edge(u, v):
                    break
            self.add_edge(u, v)
        return self

    def create_barabasi_graph(self, N=10, m0=2, m=2):
        self.expect_undirected()

        for v in range(1, m0 + 1):
            self.add_vertex(v)
        self = self.complete_graph()

        # create complete graph with m0 vertices

        step = N - m0
        for _ in range(1, step + 1):
            # add a new vertex with m edges
            u = m0 + _
            self.add_vertex(u)

            # attach to a vertex using preferential attachment
            edges = self.edges()
            for i in range(1, m + 1):
                # NOTE: degree-preferential attachment is realized by
                # selecting a vertex connected to a randomly-chosen edge.
                edge = random.choice(edges)
                v = edge[random.randrange(0, 2)]
                self.add_edge(u, v)
        return self

    def create_barabasi_random_graph(self, N=10, E=20, m0=2):
        self.expect_undirected()

        # create complete graph with m0 vertices
        for v in range(1, m0 + 1):
            self.add_vertex(v)
        self = self.complete_graph()

        # calcurate number of edges to be connected per vertex
        E0 = m0 * (m0 - 1) / 2
        nedges = (E - E0) / (N - m0)

        # add remaining (N - m0) vertices
        for u in range(m0 + 1, N + 1):
            self.add_vertex(u)

            # attach to a vertex using preferential attachment
            # NOTE: degree-preferential attachment is realized by
            # selecting a vertex connected to a randomly-chosen edge.
            edges = self.edges()
            while True:
                edge = random.choice(edges)
                v = edge[random.randrange(0, 2)]
                self.add_edge(u, v)

                # NOTE: using the fact that the average number of
                # successes of infinite Bernoulli traials with probability
                # p is given by 1/p.
                if random.uniform(0, 1) <= 1 / nedges:
                    break
        return self

    def create_ring_graph(self, N=10, step=1):
        for v in range(1, N + 1):
            self.add_vertex(v)

        # add (N - 1) edges for making circular topology
        for _ in range(0, N):
            u = _ + 1
            v = ((_ + step) % N) + 1
            self.add_edge(u, v)

        return self

    def create_tree_graph(self, N=10):
        self.add_vertex(1)

        # add (N - 1) edges for _ in making tree topology:
        for v in range(2, N + 1):
            u = random.randrange(1, v)
            self.add_edge(u, v)

        return self

    # binary tree graph
    def create_btree_graph(self, N=10):
        depth = 0
        nedges = 1
        finished = False
        while not finished:
            vleft = 2**depth
            for count in range(1, 2**depth + 1):
                v = vleft + (count - 1)
                parent = int(v / 2)
                if (parent == 0):
                    continue
                self.add_edge(v, parent)
                self.set_vertex_attribute(v, 'latent', 1 / depth)
                nedges += 1
                if nedges >= N:
                    finished = True
                    break
            depth += 1
        return self

    # tree BA graph
    def create_treeba_graph(self, N=10, alpha=1):
        self.expect_directed()
        attract = []

        # create an initial vertex
        self.add_vertex(1)
        attract[1] = alpha + self.in_edges(1)

        # create a vertex and attach to another using preferential attachment
        for u in range(2, N + 1):

            # randomly choose a vertex with a probability proportional to attract
            total = 0
            for _ in attract:
                total += _ or 0
            frac = random.uniform(0, total)
            sum = 0
            for v in range(1, N):
                sum += attract[v]
                if frac < sum:
                    self.add_edge(u, v)
                    attract[u] = alpha + self.in_edges(u)
                    attract[v] = alpha + self.in_edges(v)
                    break
        return self

    # Generalized BA model proposed in S. N. Dorogovtsev, ``Structure of
    # growing networks with preferential linking,'' Phisical Review
    # Letters, vol. 85, no. 21, pp. 4633 -= 14636, Nov. 2000.
    def create_generalized_barabasi_graph(self, N=10, m0=2, m=2, gamma=3):
        self.expect_directed()
        A = m * (gamma - 2)

        # create complete graph with m0 vertices
        self.add_vertices([v for v in range(1, m0 + 1)])
        self = self.complete_graph()

        step = N - m0
        for _ in range(1, step + 1):
            # add a new vertex with m edges
            u = m0 + _
            self.add_vertex(u)

            # attach to a vertex using preferential attachment
            vcount = self.vertices() - 1
            ecount = self.edges()
            for _ in range(1, m + 1):
                # NOTE: preferential-attachement with probability A + in_degree
                total = A * vcount + ecount
                thresh = random.uniform(0, total)
                sum = 0
                for v in range(1, u):
                    sum += A + self.in_degree(v)
                    if sum >= thresh:
                        # make sure newly added node has at least single link
                        if _ == 1:
                            self.add_edge(u, v)
                        else:
                            self.add_edge(random.randrange(1, u + 1), v)
                        break

        return self

    def create_latent_graph(self,
                            N=10,
                            E=20,
                            error_ratio=0,
                            confer='linear',
                            dist='normal',
                            alpha=10):
        # assign latent variables
        alist = []
        if dist == 'uniform':
            alist = [random.uniform(0, 1) for _ in range(N)]
        if dist == 'normal':
            alist = [random.normalvariate(1 / 2, 1 / 6) for _ in range(N)]
        if dist == 'exponential':
            alist = [random.expovariate(1 / 3) for _ in range(N)]

        alist = sorted(alist)
        for _ in range(1, N + 1):
            self.set_vertex_attribute(_, 'latent', alist[_ - 1])

        nedges = 0
        while nedges < E * (1 - error_ratio):
            u = random.randrange(1, N + 1)
            v = random.randrange(1, N + 1)
            if u == v:
                continue
            lu = self.get_vertex_attribute(u, 'latent')
            lv = self.get_vertex_attribute(v, 'latent')
            prob = 1.0
            if confer == 'abs':
                prob = lv
            elif confer == 'binary':
                if lv <= lu:
                    prob = 0
            elif confer == 'linear':
                if lv > lu:
                    prob = lv - lu
                else:
                    prob = 0
            elif confer == 'sigmoid':
                prob = 1 / (1 + math.exp(-alpha * (lv - lu)))

            if not random.uniform(0, 1) <= prob:
                continue
            self.add_edge(u, v)
            nedges += 1

        ## add disturbance
        while nedges < E:
            u = random.randrange(1, N + 1)
            v = random.randrange(1, N + 1)
            if u == v:
                continue
            self.add_edge(u, v)
            nedges += 1

        return self

    def _lattice_vertex(self, dim, n, *positions):
        v = 0
        for i in positions:
            v *= n
            if i > n:
                i -= n
            if i < 1:
                i += n
            v += i - 1
        return v + 1

    def create_lattice_graph(self, dim=2, n=5, is_torus=False):
        if dim == 1:
            for i in range(1, n + 1):
                u = self._lattice_vertex(dim, n, i)
                v = self._lattice_vertex(dim, n, i + 1)
                if is_torus or v > u:
                    self.add_edge(u, v)

        elif dim == 2:
            for j in range(1, n + 1):
                for i in range(1, n + 1):
                    u = self._lattice_vertex(dim, n, i, j)
                    v = self._lattice_vertex(dim, n, i + 1, j)
                    if is_torus or v > u:
                        self.add_edge(u, v)
                    v = self._lattice_vertex(dim, n, i, j + 1)
                    if is_torus or v > u:
                        self.add_edge(u, v)

        return self

    def create_voronoi_graph(self, npoints=10, width=1, height=1):
        points = [(random.uniform(0, width), random.uniform(0, height))
                  for n in range(npoints)]
        polys = pytess.voronoi(points)
        vmax = 1
        vmap = {}
        for orig_pnt, voronoi_pnts in polys:
            for pnt in voronoi_pnts:
                if pnt not in vmap:
                    vmap[pnt] = vmax
                    vmax += 1
            last_pnt = None
            for pnt in voronoi_pnts:
                self.add_vertex(vmap[pnt])
                x, y = pnt
                # FIXME: quick hack to pack within WIDTH x HEIGHT field
                x = max(min(x, width), 0)
                y = max(min(y, height), 0)
                self.set_vertex_attribute(vmap[pnt], 'pos', f"{x},{y}")
                if last_pnt:
                    self.add_edge(vmap[last_pnt], vmap[pnt])
                last_pnt = pnt
        return self

    def create_degree_bounded_graph(self, N=10, E=20):
        """Generate a DB (Degree-Bounded) random network with N vertices and E
        edges.  For details of the algorithm, refer to K. Yamashita et al.,
        `Revisiting the Robustness of Complex Networks against Random Node
        Removal,' Journal of Information Processing, 2019."""
        self.expect_undirected()
        k = 2 * E / N  # average degree
        kmin = int(k / 2)  # minimum degree
        if k != kmin * 2:
            die(f"Average degree {k} must be multiple of 2")

        # initially add N vertices
        self.add_vertices(*range(1, N + 1))

        for u in self.vertices():
            # randomly connect with other KMIN vertices to make sure that the
            # minimum degree is no less than KMIN.
            V = self.vertices()
            V.remove(u)
            for _ in range(kmin):
                v = random.choice(V)
                self.add_edge(u, v)
                V.remove(v)

        return self

    def create_configuration_graph(self, degree_seq=None):
        """Generate a graph using Newman's configuration model.  DEGREE_SEQ is
        a list of degrees for every vertex.  Different from common
        implementations, this code never generates self-loops and multi-edges."""

        def _connect_randomly(N, stubs_):
            self.__init__(directed=False)
            self.add_vertices(*range(1, N + 1))

            # randomly connect two stubs while prohibiting self-loops and multi-edges.
            stubs = stubs_.copy()
            random.shuffle(stubs)
            while stubs:
                u = stubs.pop()
                ntries = 0
                while True:
                    v = stubs.pop()
                    if u != v and not self.has_edge(u, v):
                        self.add_edge(u, v)
                        break
                    else:
                        # FIXME: rewrite with deque for better efficiency
                        stubs = [v] + stubs
                        ntries += 1
                        if ntries > len(stubs):
                            return False
            return True

        if degree_seq is None:
            degree_seq = [4, 3, 3, 2, 1, 1, 1]
        self.expect_undirected()

        # first, allocate stubs (i.e., connectors) for every vertex.  If the degree
        # of vertex v is k, STUB has the number k of v's; e.g., if the degree of vertex
        # 4 is 3, STUB contains three 4's.
        stubs = []
        for i, k in enumerate(degree_seq):
            stubs += [i + 1] * k
        if len(stubs) % 2:
            die(f'Total degree must be even.')

        N = len(degree_seq)
        # loop until a realization is obtained
        # FIXME: this code might loop indetinitely
        while True:
            if _connect_randomly(N, stubs):
                break
        return self

    def create_random_regular_graph(self, N=10, k=3):
        degree_seq = [k] * N
        return self.create_configuration_graph(degree_seq)

    def create_li_maini_graph(self, T=200, M=4, m0=4, m=1, alpha=.1, n=1):
        """Create a graph with M clusters using the evolutionary network
        generation model: C. Li and P. K. Maini, ``An evolving network model
        with community structure,'' Journal of Physics, 2005.  

        Parameters:
          T: the number of steps
          M: the number of initial communities
          m0: the number of vertices in each initial community
          m: the number inner-edges added per every step
          alpha: the probability of adding inter-edges
          n: the number of inter-edges added per every step"""
        self.expect_undirected()

        vmax = 0
        # community of a vertex
        community_of = {}
        # vertices in a community
        vertices_in = [[] for _ in range(M)]
        # the number of links of a vertex closed within its community
        inner_degree = {}
        # the number of links of a vertex connected with other communities
        inter_degree = {}

        def _create_vertex_in(c):
            """Create a new vertex and initialize its attributes."""
            nonlocal vmax
            vmax += 1
            v = vmax
            self.add_vertex(v)
            inner_degree[v] = 0
            inter_degree[v] = 0
            community_of[v] = c
            vertices_in[c].append(v)
            return v

        def _add_edge(u, v):
            """Add an edge between vetex U and vertex V while updating their
            attributes."""
            self.add_edge(u, v)
            if community_of[u] == community_of[v]:
                inner_degree[u] += 1
                inner_degree[v] += 1
            else:
                inter_degree[u] += 1
                inter_degree[v] += 1

        # 1. initialization
        # start from a small number m0 of fully connected nodes in each
        # community
        for c in range(M):
            for _ in range(m0):
                v = _create_vertex_in(c)
            for u, v in itertools.combinations(vertices_in[c], 2):
                _add_edge(u, v)

        # use M(M-1)/2 inter-community links to connect each community to the
        # other M-1 communities
        for c1, c2 in itertools.combinations(range(M), 2):
            # the nodes that the inter-community links connected to are
            # selected randomly in each community
            u, v = random.choice(vertices_in[c1]), random.choice(
                vertices_in[c2])
            _add_edge(u, v)

        # 2. growth
        for t in range(T):
            # at each time step, a new node is added to a randomly selected
            # community
            c = random.randrange(M)
            u = _create_vertex_in(c)

            # 3. preferential attachments
            # the new node will be connected to m nodes in the same community
            # through m inner-community links
            degrees = [inner_degree[v] for v in vertices_in[c]]
            total = sum(degrees)
            prob = [d / total for d in degrees]
            for v in numpy.random.choice(vertices_in[c],
                                         size=m,
                                         replace=False,
                                         p=prob):
                _add_edge(u, v)

            # with probability alpha connected to n nodes (none with
            # probability 1 - alpha) in the other M - 1 communities through
            # inter-community links
            if random.random() <= alpha:
                vertices = []
                degrees = []
                for v in self.vertices():
                    if community_of[v] != c:
                        vertices.append(v)
                        degrees.append(inter_degree[v])
                total = sum(degrees)
                prob = [d / total for d in degrees]
                for v in numpy.random.choice(vertices,
                                             size=m,
                                             replace=False,
                                             p=prob):
                    _add_edge(u, v)

    # import ----------------------------------------------------------------
    def import_graph(self, fmt, *args):
        name = IMPORT_SUBP.get(fmt, None)
        method = getattr(self, name, None)
        if not name or not method:
            die(f"No import support for graph format `{fmt}'")
        return method(*args)

    def import_dot(self, lines):
        buf = ''
        for line in lines:
            # remove C++-style comment
            pos = line.find('//')
            if pos >= 0:
                line = line[pos:]
            line = line.strip()
            buf += line
        # remove C-style comment
        buf = re.sub(r'/\*.*?\*/', '', buf)
        m = re.search(r'graph\s+(\S+)\s*{(.*)}', buf)
        if not m:
            die('Invalid graph format (missing dot graph header)')
        body = m.group(2)
        return self._import_dot_body(body)

    def _import_dot_body(self, body_str):
        for line in body_str.split(';'):
            line = line.strip()
            if not line:
                continue
            if 'graph' in line or 'node' in line or 'edge' in line:
                continue
            m = re.match(r'([^\[]*)\s*(\[(.*)\])?', line)
            if not m:
                continue

            val, opts = m.group(1), m.group(3) or ''
            val = val.replace('\"', '')

            # parse attributes [name1=val1,name2=val2...]
            attrs = {}
            for pair in opts.split(','):
                if not pair:
                    break
                akey, aval = pair.split('=', 2)
                attrs[akey] = aval.replace('\"', '')

            # parse vertex/edge definition
            # FIXME: this might be problematic...
            if '--' in val or '->' in val:  # vertex -- vertex [-- vertex...]
                vertices = re.split(r'\s*-[->]\s*', val)
                while len(vertices) >= 2:
                    u, v = vertices[0], vertices[1]
                    u, v = str2number(u), str2number(v)
                    i = self.add_edge_get_id(u, v)
                    self.set_edge_attributes_by_id(u, v, i, attrs)
                    vertices.pop(0)
            else:  # vertex
                v = str2number(val)
                self.add_vertex(v)
                self.set_vertex_attributes(v, attrs)

    def import_dot_quick(self, listp):
        raise NotImplementedError

    def import_dimacs(self, listp):
        raise NotImplementedError

    def import_inet(self, listp):
        raise NotImplementedError

    def import_brite(self, listp):
        raise NotImplementedError

    def import_gw(self, listp):
        raise NotImplementedError

    def import_nsnode(self, listp):
        raise NotImplementedError

    def import_nsagent(self, listp):
        raise NotImplementedError

    def import_metis(self, listp):
        raise NotImplementedError

    def import_edge(self, listp):
        raise NotImplementedError

    def import_cell(self, listp):
        raise NotImplementedError

    # ----------------------------------------------------------------

    def export_graph(self, fmt, *args):
        name = EXPORT_SUBP.get(fmt, None)
        method = getattr(self, name, None)
        if not name or not method:
            die(f"No export support for graph format `{fmt}'")
        return method(*args)

    def export_dot(self, *args):
        astr = self.header_string('// ')
        head = 'digraph' if self.is_directed() else 'graph'
        astr += head + ' export_dot {\n  node [color=gray90,style=filled];\n'
        for v in sorted(self.vertices()):
            astr += f'  "{v}"'
            attrs = self.get_vertex_attributes(v)
            if attrs:
                alist = []
                for key, val in attrs.items():
                    alist.append(f'{key}="{val}"')
                astr += ' [' + (', '.join(alist)) + ']'
            astr += ';\n'

        for edge in sorted(self.unique_edges(), key=lambda e: e[0]):
            u = edge[0]
            v = edge[1]
            if self.undirected() and v < u:
                u, v = v, u
            l = '->' if self.is_directed() else '--'
            for i in self.get_multiedge_ids(u, v):
                astr += f'  "{u}" {l} "{v}"'
                attrs = self.get_edge_attributes_by_id(u, v, i)
                if attrs:
                    alist = []
                    for key, val in attrs.items():
                        alist.append(f'{key}="{val}"')
                    astr += ' [' + (', '.join(alist)) + ']'
                astr += ';\n'
        astr += '}\n'
        return astr

    def export_dimacs(self):
        raise NotImplementedError

    def export_inet(self):
        raise NotImplementedError

    def export_brite(self):
        raise NotImplementedError

    def export_gw(self):
        raise NotImplementedError

    def export_nsnode(self):
        raise NotImplementedError

    def export_nsagent(self):
        raise NotImplementedError

    def export_nsagent_edge(self, N):
        raise NotImplementedError

    def export_nsagent_udp(self):
        raise NotImplementedError

    def export_metis(self):
        raise NotImplementedError

    def is_included(v, partp, n):
        raise NotImplementedError

    # return IP address of link U-V at side W in N-th partition
    # FIXME: assuming number of nodes < 256
    def get_link_ipaddr(u, v, w, n):
        raise NotImplementedError

    # return IP address of remote link U-V at side W
    # FIXME: assuming number of nodes < 256
    def get_rlink_ipaddr(u, v, w):
        raise NotImplementedError

    def export_pdnsnode(self, partp, n):
        raise NotImplementedError

    def export_pdnsagent(T, partp, n, self):
        raise NotImplementedError

    def export_gdl(self):
        raise NotImplementedError

    def export_cell(self):
        raise NotImplementedError

    is_directed = directed
    is_undirected = undirected
    is_multiedged = multiedged
    add_edge_get_id = add_edge
    out_edges = edges_from
    in_edges = edges_to

def main():
    g = Graph()
    g.create_voronoi_graph()
    s = g.export_dot()
    print(s)
    raise

if __name__ == "__main__":
    main()