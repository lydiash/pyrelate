import numpy as np
'''Built-in descriptors for use with AtomsCollection's describe function.

Some guidelines for writing your own descriptor function
    - Some descriptions (including built in ASR and LER) require previously computed results, if you want to write your own descriptor function that accesses the store, one of your included parameters must be 'store'. 'Res_needed' is also a suggested parameter to include, it indicates which results to use when computing the new descriptor.
'''


def soap(atoms, rcut, nmax, lmax, **kwargs):
    """Smooth Overlap of Atomic Positions-- pycsoap implementation

    Parameters:
        atoms ('ase.atoms.Atoms'): ASE atoms object to perform description on
        nmax (int): bandwidth limits for the SOAP descriptor radial basis functions.
        lmax (int): bandwidth limits for the SOAP descriptor spherical harmonics.
        rcut (float): local environment finite cutoff parameter.
        kwargs (dict): Parameters associated with the description function

    To see `pycsoap's documentation <https://pypi.org/project/pycsoap/>`_.
    """
    from pycsoap.soaplite import SOAP
    soap_desc = SOAP(atomic_numbers=atoms.numbers, rcut=rcut,
                     nmax=nmax, lmax=lmax, **kwargs)
    P = soap_desc.create(atoms)
    return P

# TODO write a sum function


def asr(atoms, store, res_needed='soap', norm_asr=False, **kwargs):
    """Average SOAP representation: average vectors from SOAP matrix into a single vector

    Parameters:
        atoms ('ase.atoms.Atoms'): ASE atoms object to perform description on
        store (pyrelate.store.Store) : store to access previously computed SOAP matrix (automatically passed in with the 'needs_info' parameter in describe())
        res_needed (str): What results to compute the ASR on. Defaults to 'soap'.
        norm_asr (bool): Normalize ASR vector. Default is False, not normalized.
    """
    magnitude = 1
    aid = atoms.get_array("aid")[0]
    matrix = store.get(
        res_needed, aid, **kwargs)
    if matrix is None:
        return None
    else:
        asr_res = np.average(matrix, axis=0)
        if norm_asr is True:
            magnitude = np.linalg.norm(asr_res)
        return asr_res / magnitude


def ler(atoms, store, collection, eps, res_needed='soap', soapfcn=None, seed=None, metric='euclidean', n_trees=10, search_k=-1, **soapargs):
    '''Local Environment Representation
    TODO fix for updated describe function

    Parameters:
        atoms ('ase.atoms.Atoms'): ASE atoms object to perform description on
        store (pyrelate.store.Store) : store to access previously computed SOAP matrix (automatically passed in with the 'needs_info' parameter in describe())
        collection (pyrelate.collection.AtomsCollection): LER is collection specific, needed for computation
        eps (float): epsilon value indicating that any LAE's outside this value are considered dissimilar
        res_needed (str): What results to compute the LER with. Defaults to 'soap'.
        soapfcn (function): optional parameter for a function to compute SOAP for perfect FCC atom, defaults to None and SOAP in descriptors.py will be used.
        seed(): perfect FCC seed for the element being considered. Defaults to None, so it will be generated on the fly.
        metric(str): For approximate nearest neighbor calculation. See annoys documentation for more details.
        n_trees(int): For approximate nearest neighbor calculation. See annoys documentation for more details.
        search_k(int): For approximate nearest neighbor calculation. See annoys documentation for more details.
        kwargs (dict): Parameters associated with the description function

    `Annoy's documentation <https://github.com/spotify/annoy>`_.

    '''
    U = store.get(
        "temp", 'U_ler', collection=collection, eps=eps, res_needed=res_needed, soapfcn=soapfcn, metric=metric, n_trees=n_trees, search_k=search_k, **soapargs)  # add seed? or hash?
    if U is None:
        from collections import OrderedDict
        U = {
            'centers': OrderedDict(),
            'clusters': {}
        }

        # Part 1: Clustering
        import pyrelate.elements as elements
        if seed is None:
            seed = elements.seed(list(collection.values())[0].get_chemical_symbols()[
                                 0], soapfcn, **soapargs)
        U['centers'][('0', 0)] = seed
        for aid in collection:
            for lae_num, lae in enumerate(store.get(res_needed, aid, **soapargs)):
                if lae is None:
                    raise RuntimeError(
                        "LER requries SOAP to be generated first")
                for unique in U['centers'].values():
                    dist = np.linalg.norm(unique - lae)
                    if dist < eps:
                        break
                else:
                    U['centers'][(aid, lae_num)] = np.copy(lae)
        # FIXME sort the unique bins

        # Part 2: Classifying
        from annoy import AnnoyIndex
        dim = len(seed)
        a = AnnoyIndex(dim, metric)
        for i, unique in enumerate(U['centers'].values()):
            a.add_item(i, unique)
        a.build(n_trees)
        a.save('tmp')  # TODO find better way to save temporary file
        for aid in collection:
            for lae_num, lae in enumerate(store.get(res_needed, aid, **soapargs)):
                nni = a.get_nns_by_vector(
                    lae, 1, search_k=search_k, include_distances=False)[0]
                cluster = list(U['centers'].keys())[nni]
                # FIXME when we sort just fill the empty lists first
                if cluster not in U['clusters']:
                    U['clusters'][cluster] = []
                U['clusters'][cluster].append((aid, lae_num))
        import os
        os.remove('tmp')

        store.store(
            U, "temp", 'U_ler', collection=collection, eps=eps, res_needed=res_needed, soapfcn=soapfcn, metric=metric, n_trees=n_trees, search_k=search_k, **soapargs)

    # Calculate LER
    aid = atoms.get_array('aid')[0]
    result = np.zeros(len(U['clusters']))
    for uid, (center, cluster) in enumerate(U['clusters'].items()):
        result[uid] = np.count_nonzero(
            np.array([c[0] for c in cluster]) == aid)
    result = result / np.sum(result)
    return result
