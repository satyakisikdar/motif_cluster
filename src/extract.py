"""
VRG extraction
"""

import random
from collections import defaultdict
import networkx as nx
import numpy as np
from time import time
from copy import deepcopy
from tqdm import tqdm
from typing import List, Tuple, Dict, DefaultDict, Set, Any

from src.Rule import FullRule
from src.Rule import NoRule
from src.Rule import PartRule
from src.globals import find_boundary_edges
from src.part_info import set_boundary_degrees
from src.VRG import VRG
from src.LightMultiGraph import LightMultiGraph
from src.Tree import TreeNode
from src.MDL import graph_mdl


def node_score_lambda(internal_node: TreeNode, lamb: int) -> int:
    '''
    returns the score of an internal node
    :param internal_node:
    :param lamb:
    :return:
    '''
    return abs(internal_node.nleaf - lamb)


def node_score_mdl(g: LightMultiGraph, subtree: List[int], mode: str):
    g_copy = g.copy()

    # step 1: find mdl of the rule's RHS graph
    rule, boundary_edges = create_rule(subtree, g_copy, mode)

    # step 2: find mdl of the graph after compression


def get_buckets(root: TreeNode, lamb: int) -> Tuple[Set[Any], DefaultDict[float, Any], Dict[float, Any]]:
    """

    :return:
    """
    bucket = defaultdict(set)  # create buckets keyed in by the absolute difference of k and number of leaves and the list of nodes_in_tree
    node2bucket = {}  # keeps track of which bucket every node in the tree is in
    nodes_in_tree = set()  # set of both internal and leaf nodes of the tree
    stack = [root]
    level = {root.key: 0}

    while len(stack) != 0:
        node =  stack.pop()
        nodes_in_tree.add(node)
        score = node_score_lambda(node, lamb)

        if not node.is_leaf:  # don't add to the bucket if it's a leaf
            bucket[score].add(node.key)   # bucket is a defaultdict
            node2bucket[node.key] = score
            for kid in node.kids:
                level[kid.key] = level[node.key] + 1
                kid.level = level[kid.key]
                stack.append(kid)

    return nodes_in_tree, bucket, node2bucket


def update_parents(node: TreeNode, buckets: DefaultDict[float, Any], node2bucket: Dict[Any, int], lamb: int) -> None:
    """

    :param node:
    :param lamb:
    :return:
    """
    # the subtree that is removed to be removed
    node_key = node.key
    subtree = node.leaves
    subtree.remove(node.key)

    while node.parent is not None:
        old_val = node2bucket[node.parent.key]  # old value of parent
        buckets[old_val].remove(node.parent.key)  # remove the parent from that bucket

        node.parent.nleaf -= node.nleaf - 1  # since all the children of the node disappears, but the node remains
        node.parent.leaves -= subtree
        node.parent.leaves.add(node_key)

        new_val = abs(node.parent.nleaf - lamb)  # new value of parent

        buckets[new_val].add(node.parent.key)   # adding the parent to a new bucket
        node2bucket[node.parent.key] = new_val   # updating the node2bucket dict

        node = node.parent
    return


def extract_subtree(lamb: int, buckets: DefaultDict[float, Any], node2bucket: Dict[Any, int], active_nodes: Set[Any],
                    key2node: Dict[Any, TreeNode], g: LightMultiGraph, mode: str, grammar: VRG, selection: str) -> Tuple[List[int], Set[int]]:
    """
    :param lamb: size of subtree to be collapsed
    :param buckets: mapping of val -> set of internal nodes in the tree
    :param node2bucket: mapping of key -> node
    :param g: graph
    :return: subtree, set of active nodes
    """

    # pick something from the smallest non-empty bucket
    best_node_key = None  # the key of the best node found from the buckets
    best_node = None

    if selection == 'mdl':
        min_key = float('inf')  # min MDL
    elif selection == 'level':
        min_key = float('inf')  # min level
    elif selection == 'level_mdl':
        min_key = (float('inf'), float('inf'))  # min_level, min_MDL
    else:  # random
        min_key = None  # pick randomly

    for _, bucket in sorted(buckets.items()):  # start with the bucket with the min value
        possible_node_keys = bucket & active_nodes  # possible nodes are the ones that are allowed

        if len(possible_node_keys) == 0:  # if there is no possible nodes, move on
            continue

        elif len(possible_node_keys) == 1:  # just one node in the bucket
            best_node_key = possible_node_keys.pop()

        else:  # the bucket has more than one node
            if selection not in ('mdl', 'level', 'level_mdl'):    # if picking randomly, and the bucket is not empty
                best_node_key = random.sample(possible_node_keys, 1)[0]  # sample 1 node from the min bucket randomly

            else:  # rule selection is non random
                is_existing_rule = False  # checks if the bucket contains any existing rules
                min_node_key = None

                for node_key in possible_node_keys:
                    subtree = key2node[node_key].leaves & active_nodes  # only consider the leaves that are active
                    rule_level = key2node[node_key].level

                    assert isinstance(rule_level, int), 'rule level not int'

                    rule, _ = create_rule(subtree=subtree, mode=mode, g=g)  # the rule corresponding to the subtree -

                    if rule in grammar:  # the rule already exists pick that
                        best_node_key = node_key
                        is_existing_rule = True
                        # print('existing rule found!')
                        break  # you dont need to look further

                    if 'mdl' in selection:
                        rule.calculate_cost()  # find the MDL cost of the rule
                    # print('node: {} mdl: {}'.format(node_key, rule.cost))

                    if selection == 'mdl':
                        if rule.cost < min_key:
                            min_key = rule.cost
                            min_node_key = node_key

                    elif selection == 'level':
                        if rule_level < min_key:
                            min_key = rule_level
                            min_node_key = node_key

                    else:   # selection is level_mdl
                        if (rule_level, rule.cost) < min_key:
                            min_key = (rule_level, rule.cost)
                            min_node_key = node_key

                if not is_existing_rule:  # all the rules were new
                    best_node_key = min_node_key

        # print('Picking node {} from the bucket level {}'.format(best_node_key, min_key[1]))
        best_node = key2node[best_node_key]
        break

    if best_node is None:
        return None, None

    subtree = best_node.leaves & active_nodes  # only consider the leaves that are active

    new_node_key = min(subtree)  # key of the new node

    active_nodes = active_nodes - best_node.children  # all the children of this node are no longer active
    active_nodes.remove(best_node.key)  # remove the old node too
    active_nodes.add(new_node_key)  # add the new node key
    best_node.key = new_node_key  # update the key

    if best_node.parent is not None:
        update_parents(node=best_node, buckets=buckets, node2bucket=node2bucket, lamb=lamb)

    best_node.make_leaf(new_key=new_node_key)  # make the node a leaf
    return subtree, active_nodes


def create_rule(subtree: List[int], g: LightMultiGraph, mode: str) -> Tuple[Any, List[int]]:
    sg = g.subgraph(subtree)
    assert isinstance(sg, LightMultiGraph)
    boundary_edges = find_boundary_edges(g, subtree)

    if mode == 'full':  # in the full information case, we add the boundary edges to the RHS and contract it
        rule = FullRule(lhs=len(boundary_edges), internal_nodes=subtree, graph=sg)

        for u, v in boundary_edges:
            rule.graph.add_edge(u, v, attr_dict={'b': True})

        rule.contract_rhs()  # contract and generalize

    elif mode == 'part':  # in the partial boundary info, we need to set the boundary degrees
        rule = PartRule(lhs=len(boundary_edges), graph=sg)
        set_boundary_degrees(g, rule.graph)
        rule.generalize_rhs()

    else:
        rule = NoRule(lhs=len(boundary_edges), graph=sg)
        rule.generalize_rhs()
    return rule, boundary_edges


def compress_graph(g: LightMultiGraph, subtree: List[int], boundary_edges: List[int]) -> None:
    '''
    Compress the subtree into one node and return the updated graph
    :param subtree:
    :param boundary_edges:
    :return:
    '''
    subtree = set(subtree)

    # step 1: remove the nodes from subtree
    g.remove_nodes_from(subtree)
    new_node = min(subtree)

    # step 2: replace subtree with new_node
    g.add_node(new_node, attr_dict={'label': len(boundary_edges)})

    # step 3: rewire new_node
    for u, v in boundary_edges:
        if u in subtree:
            u = new_node
        if v in subtree:
            v = new_node
        g.add_edge(u, v)


def extract(g: LightMultiGraph, root: TreeNode, lamb: int, selection: str, mode: str, clustering: str, name: str) -> VRG:
    """
    Runner function for the funcky extract
    :param g: graph
    :param root: pointer to the root of the tree
    :param lamb: number of leaves to collapse
    :param mode: full / part / no

    :return: list of rules
    """
    # start_time = time()

    nodes, buckets, node2bucket = get_buckets(root=root, lamb=lamb)
    active_nodes = {node.key for node in nodes}  # all nodes in the tree
    key2node = {node.key: node for node in nodes}   # key -> node mapping

    tree_nodes_count = len(active_nodes)

    grammar = VRG(mode=mode, lamb=lamb, selection=selection, clustering=clustering, name=name)
    print('Grammar extraction progress')

    with tqdm(total=100, bar_format='{l_bar}{bar}|[{elapsed}<{remaining}]', ncols=50) as pbar:
        while True:
            subtree, active_nodes = extract_subtree(lamb=lamb, buckets=buckets, node2bucket=node2bucket, key2node=key2node,
                                                    active_nodes=active_nodes, g=g, mode=mode, grammar=grammar,
                                                    selection=selection)
            # print('Subtree: ', subtree)
            if subtree is None:
                break

            rule, boundary_edges = create_rule(subtree=subtree, mode=mode, g=g)
            assert len(boundary_edges) == rule.lhs

            if rule.lhs == 0 and rule.graph.size() == 0:  # this prevents the dummy start rule
                break
            grammar.add_rule(rule)

            percent = (1 - len(active_nodes) / tree_nodes_count) * 100
            pbar.update(percent - pbar.n)

            compress_graph(g, subtree, boundary_edges)


    # end_time = time()

    # print('\nGrammar extracted in {} secs'.format(round(end_time - start_time, 3)))

    return grammar


def extract_subtree_mdl(g: LightMultiGraph, root: TreeNode, mode: str):
    '''
    extract the subtree based on mdl
    :param g:
    :param root:
    :param active_nodes: nodes that are presently active
    :return:
    '''
    # step 1: compute score for each tree node: mdl(G) / (mdl(G | S) + mdl(S))

    active_nodes = set(g.nodes_iter())
    stack: List[TreeNode] = [root]
    best_node = None
    best_score = float('-inf')

    while len(stack) != 0:
        node =  stack.pop()
        g_copy = g.copy()
        mdl_g = graph_mdl(g_copy)

        subtree = node.leaves & active_nodes

        rule, boundary_edges = create_rule(subtree, g_copy, mode)
        rule.calculate_cost()

        mdl_s = rule.cost

        compress_graph(g_copy, subtree, boundary_edges)
        mdl_g_s = graph_mdl(g_copy)
        score = mdl_g / (mdl_g_s + mdl_s)
        # print(f'node: {node.key}, subtree: {subtree}, rule: {rule}, score: {round(score, 3)}')

        if score > best_score:
            best_score = score
            best_node = node

        for kid in node.kids:
            if not kid.is_leaf:  # don't add to the bucket if it's a leaf
                stack.append(kid)
    print(f'best node: {best_node}, score: {round(best_score, 3)}')
    # step 2: pick largest
    best_subtree = best_node.leaves & active_nodes

    # step 3: update the tree
    best_node.make_leaf(new_key=min(best_subtree))
    return best_subtree


def extract_mdl(g: LightMultiGraph, root: TreeNode, selection: str, mode: str, clustering: str, name: str) -> VRG:
    '''
    # do the funky MDL thing

    :return:
    '''
    grammar = VRG(mode=mode, selection=selection, clustering=clustering, name=name)

    while True:
        subtree = extract_subtree_mdl(g, root, mode)
        print('subtree:', subtree)

        rule, boundary_edges = create_rule(subtree, g, mode)
        grammar.add_rule(rule)
        compress_graph(g, subtree, boundary_edges)

        if g.order() == 1:
            break
    return grammar
