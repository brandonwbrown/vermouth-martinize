# -*- coding: utf-8 -*-
# Copyright 2018 University of Groningen
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Created on Tue Aug 22 11:33:07 2017

@author: Peter Kroon
"""
from ..molecule import Molecule
from ..utils import first_alpha, distance
from ..truncating_formatter import TruncFormatter

from functools import partial

import numpy as np


def get_not_none(node, attr, default):
    value = node.get(attr)
    if value is None:
        value = default
    return value


def write_pdb_string(system, conect=True):
    def keyfunc(graph, node_idx):
        # TODO add something like idx_in_residue
        return graph.node[node_idx]['chain'], graph.node[node_idx]['resid'], graph.node[node_idx]['resname']

    out = []

    formatter = TruncFormatter()
#    format_string = 'ATOM  {: >5.5d} {:4.4s}{:1.1s}{:3.3s} {:1.1s}{:4.4d}{:1.1s}   {:8.3f}{:8.3f}{:8.3f}{:6.2f}{:6.2f}          {:2.2s}{:2.2s}'
    format_string = 'ATOM  {: >5dt} {:4st}{:1st}{:3st} {:1st}{:>4dt}{:1st}   {:8.3ft}{:8.3ft}{:8.3ft}{:6.2ft}{:6.2ft}          {:2st}{:2st}'
    
    # FIXME Here we make the assumption that node indices are unique across
    # molecules in a system. Probably not a good idea
    nodeidx2atomid = {}
    atomid = 1
    for molecule in system.molecules:
        node_order = sorted(molecule, key=partial(keyfunc, molecule))

        for node_idx in node_order:
            nodeidx2atomid[node_idx] = atomid
            node = molecule.node[node_idx]
            atomname = node['atomname']
            altloc = get_not_none(node, 'altloc', '')
            resname = node['resname']
            chain = node['chain']
            resid = node['resid']
            insertion_code = get_not_none(node, 'insertioncode', '')
            x, y, z = node['position'] * 10  # converting from nm to A
            occupancy = get_not_none(node, 'occupancy', 1)
            temp_factor = get_not_none(node, 'temp_factor', 0)
            element = get_not_none(node, 'element', '')
            charge = get_not_none(node, 'charge', 0)
            if charge:
                charge = '{:+2d}'.format(int(charge))[::-1]
            else:
                charge = ''
            line = formatter.format(format_string, atomid, atomname, altloc,
                                    resname, chain, resid, insertion_code, x,
                                    y, z, occupancy, temp_factor, element,
                                    charge)
            atomid += 1
            out.append(line)
        terline = formatter.format('TER   {: >5dt}      {:3st} {:1st}{: >4dt}{:1st}',
                                   atomid, resname, chain, resid, insertion_code)
        atomid += 1
        out.append(terline)
    if conect:
        number_fmt = '{:>4dt}'
        format_string = 'CONECT '
        for molecule in system.molecules:
            node_order = sorted(molecule, key=partial(keyfunc, molecule))

            for node_idx in node_order:
                todo = [nodeidx2atomid[n_idx] for n_idx in molecule[node_idx]]
                while todo:
                    current, todo = todo[:4], todo[4:]
                    fmt = ['CONECT'] + [number_fmt]*(len(current) + 1)
                    fmt = ' '.join(fmt)
                    line = formatter.format(fmt, nodeidx2atomid[node_idx], *current)
                    out.append(line)
    out.append('END   ')
    return '\n'.join(out)


def write_pdb(system, path, conect=True):
    with open(path, 'w') as out:
        out.write(write_pdb_string(system, conect))


def do_conect(mol, conectlist):
    """Apply connections to molecule based on CONECT records read from PDB file"""
    atidx2nodeidx = {node_data['atomid']: node_idx
                     for node_idx, node_data in mol.node.items()}

    for line in conectlist:
        start = 6
        width = 5
        ats = []
        for num in range(start, len(line.rstrip()), width):
            at = int(line[num:num + width])
            ats.append(at)
            try:
                at0 = atidx2nodeidx[ats[0]]
            except KeyError:
                continue
            for at in ats[1:]:
                try:
                    at = atidx2nodeidx[at]
                except KeyError:
                    continue
                dist = distance(mol.node[at0]['position'], mol.node[at]['position'])
                mol.add_edge(at0, at, distance=dist)

    return

                    
def read_pdb(file_name, exclude=('SOL',), ignh=False, model=0):
    models = [Molecule()]
    conect = []
    idx = 0
    
    field_widths = (-6, 5, -1, 4, 1, 4, 1, 4, 1, -3, 8, 8, 8, 6, 6, -10, 2, 2)
    field_types = (int, str, str, str, str, int, str, float, float, float, float, float, str, str)
    field_names = ('atomid', 'atomname', 'altloc', 'resname', 'chain', 'resid',
                   'insertion_code', 'x', 'y', 'z', 'occupancy', 'temp_factor',
                   'element', 'charge')

    start = 0
    slices = []
    for width in field_widths:
        if width > 0:
            slices.append(slice(start, start + width))
        start = start + abs(width)
    
    with open(file_name) as pdb:
        for line in pdb:
            record = line[:6]
            if record == 'ENDMDL':
                models.append(Molecule())
            elif record == 'ATOM  ' or record == 'HETATM':
                properties = {}
                for name, type_, slice_ in zip(field_names, field_types, slices):
                    properties[name] = type_(line[slice_].strip())

                pos = (properties.pop('x'), properties.pop('y'), properties.pop('z'))
                # Coordinates are read in Angstrom, but we want them in nm
                properties['position'] = np.array(pos, dtype=float) / 10

                if not properties['element']:
                    atomname = properties['atomname']
                    properties['element'] = first_alpha(atomname)
                if properties['resname'] in exclude or (ignh and properties['element'] == 'H'):
                    continue
                models[-1].add_node(idx, **properties)
                idx += 1
            elif record == 'CONECT':
                conect.append(line)

    if not len(models[-1]):
        models.pop()
        
    for molecule in models:
        do_conect(molecule, conect)
                
    molecule = models[model]

#    if molecule.number_of_edges() == 0:
#        edges_from_distance(molecule)
#        # Make all edges based on threshold distance
#        positions = np.array([molecule.node[n]['position'] for n in molecule])
#        distances = ssd.squareform(ssd.pdist([molecule.node[n]['position'] for n in molecule]))
#        idxs = np.where((distances < threshold) & (distances != 0))
#        weights = 1/distances[idxs]
#        molecule.add_weighted_edges_from(zip(idxs[0], idxs[1], weights))

    return molecule
