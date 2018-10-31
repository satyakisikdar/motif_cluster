import networkx as nx
import os
import platform
import subprocess
import pandas as pd
import scipy.stats
import scipy.spatial
import numpy as np

def GCD(h1, h2, mode='rage'):
    if mode == 'rage':
        df_g = external_rage(h1, 'orig')
        df_h = external_rage(h2, 'test')
    else:
        df_g = external_orca(h1, 'orig')
        df_h = external_orca(h2, 'test')

    gcm_g = tijana_eval_compute_gcm(df_g)
    gcm_h = tijana_eval_compute_gcm(df_h)

    gcd = tijana_eval_compute_gcd(gcm_g, gcm_h)
    return round(gcd, 3)


def external_orca(g, gname):
    g = nx.Graph(g)  # convert it into a simple graph
    g = max(nx.connected_component_subgraphs(g), key=len)
    g = nx.convert_node_labels_to_integers(g, first_label=0)

    file_dir = 'tmp'
    with open('./{}/{}.in'.format(file_dir, gname), 'w') as f:
        f.write('{} {}\n'.format(g.order(), g.size()))
        for u, v in g.edges_iter():
            f.write('{} {}\n'.format(u, v))

    args = './orca', '4', './{}/{}.in'.format(file_dir, gname), './{}/{}.out'.format(file_dir, gname)

    popen = subprocess.Popen(args, stdout=subprocess.DEVNULL)
    popen.wait()

    df = pd.read_csv('{}/{}.out'.format(file_dir, gname), sep=' ', header=None)
    return df


def external_rage(G, netname):
    G = nx.Graph(G)
    G = max(nx.connected_component_subgraphs(G), key=len)

    tmp_file = "tmp_{}.txt".format(netname)
    with open(tmp_file, 'w') as tmp:
        for e in G.edges_iter():
            tmp.write(str(int(e[0]) + 1) + ' ' + str(int(e[1]) + 1) + '\n')

    if 'Windows' in platform.platform():
        args = ("./RAGE_windows.exe", tmp_file)
    elif 'Linux' in platform.platform():
        args = ('./RAGE_linux.dms', tmp_file)
    else:
        args = ("./RAGE.dms", tmp_file)

    popen = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    popen.wait()

    # Results are hardcoded in the exe
    df = pd.read_csv('./Results/UNDIR_RESULTS_tmp_{}.csv'.format(netname),
                     header=0, sep=',', index_col=0)
    df = df.drop('ASType', 1)
    return df


def tijana_eval_compute_gcm(G_df):
    l = G_df.shape[1]  # no of graphlets: #cols in G_df

    M = G_df.as_matrix()  # matrix of nodes & graphlet counts
    M = np.transpose(M)  # transpose to make it graphlet counts & nodes
    gcm = scipy.spatial.distance.squareform(   # squareform converts the sparse matrix to dense matrix
        scipy.spatial.distance.pdist(M,   # compute the pairwise distances in M
                                     lambda x, y: scipy.stats.spearmanr(x, y)[0]))  # using spearman's correlation
    gcm = gcm + np.eye(l, l)   # make the diagonals 1 (dunno why, but it did that in the original code)
    return gcm


def tijana_eval_compute_gcd(gcm_g, gcm_h):
    assert len(gcm_h) == len(gcm_g), "Correlation matrices must be of the same size"

    gcd = np.sqrt(   # sqrt
        np.sum(  # of the sum of elements
            (np.triu(gcm_g) - np.triu(gcm_h)) ** 2   # of the squared difference of the upper triangle values
        ))

    return gcd