# -*- coding: utf-8 -*-
"""
Created on Fri Jun 21 13:24:31 2019

@author: gbuster
"""
import concurrent.futures as cf
import os
import h5py
import numpy as np
import pandas as pd
from warnings import warn
import logging

from reV.handlers.outputs import Outputs
from reV.supply_curve.tech_mapping import TechMapping
from reV.supply_curve.points import (ExclusionPoints, SupplyCurvePoint,
                                     SupplyCurveExtent)
from reV.utilities.exceptions import EmptySupplyCurvePointError, OutputWarning


logger = logging.getLogger(__name__)


class SupplyCurvePointSummary(SupplyCurvePoint):
    """Supply curve summary framework with extra methods for summary calc."""

    def latitude(self):
        """Get the SC point latitude"""
        return self.centroid[0]

    def longitude(self):
        """Get the SC point longitude"""
        return self.centroid[1]

    def res_gids(self):
        """Get the list of resource gids corresponding to this sc point.

        Returns
        -------
        res_gids : list
            List of resource gids.
        """
        return list(set(self._res_gids))

    def gen_gids(self):
        """Get the list of generation gids corresponding to this sc point.

        Returns
        -------
        gen_gids : list
            List of generation gids.
        """
        return list(set(self._gen_gids))

    @classmethod
    def summary(cls, gid, fpath_excl, fpath_gen, fpath_techmap, args=None,
                **kwargs):
        """Get a summary dictionary of a single supply curve point.

        Parameters
        ----------
        gid : int
            gid for supply curve point to analyze.
        fpath_excl : str
            Filepath to exclusions geotiff.
        fpath_gen : str
            Filepath to .h5 reV generation output results.
        fpath_techmap : str
            Filepath to tech mapping between exclusions and generation results
            (created using the reV TechMapping framework).
        args : tuple | list | None
            List of summary arguments to include. None defaults to all
            available args defined in the class attr.
        kwargs : dict
            Keyword args to init the SC point.

        Returns
        -------
        summary : dict
            Dictionary of summary outputs for this sc point.
        """

        with cls(gid, fpath_excl, fpath_gen, fpath_techmap, **kwargs) as point:

            ARGS = {'resource_gids': point.res_gids,
                    'gen_gids': point.gen_gids,
                    'latitude': point.latitude,
                    'longitude': point.longitude,
                    }

            if args is None:
                args = list(ARGS.keys())

            summary = {}
            for arg in args:
                if arg in ARGS:
                    summary[arg] = ARGS[arg]()
                else:
                    warn('Cannot find "{}" as an available SC point summary '
                         'output', OutputWarning)

        return summary


class Aggregation:
    """Supply points aggregation framework."""

    @staticmethod
    def _serial_summary(fpath_excl, fpath_gen, fpath_techmap, resolution=64,
                        gids=None):
        """Standalone method to create agg summary - can be parallelized.

        Parameters
        ----------
        fpath_excl : str
            Filepath to exclusions geotiff.
        fpath_gen : str
            Filepath to .h5 reV generation output results.
        fpath_techmap : str
            Filepath to tech mapping between exclusions and generation results
            (created using the reV TechMapping framework).
        resolution : int | None
            SC resolution, must be input in combination with gid. Prefered
            option is to use the row/col slices to define the SC point instead.
        gids : list | None
            List of gids to get summary for (can use to subset if running in
            parallel), or None for all gids in the SC extent.

        Returns
        -------
        summary : dict
            Summary dictionary of the SC points keyed by SC point gid.
        """

        summary = {}

        with SupplyCurveExtent(fpath_excl, resolution=resolution) as sc:

            if gids is None:
                gids = range(len(sc))

            # pre-extract handlers so they are not repeatedly initialized
            with ExclusionPoints(fpath_excl) as excl:
                with Outputs(fpath_gen, mode='r') as gen:
                    with h5py.File(fpath_techmap, 'r') as techmap:

                        for gid in gids:
                            try:
                                pointsum = SupplyCurvePointSummary.summary(
                                    gid, excl, gen, techmap,
                                    resolution=resolution,
                                    exclusion_shape=sc.exclusions.shape,
                                    close=False)

                            except EmptySupplyCurvePointError as _:
                                pass

                            else:
                                pointsum['sc_gid'] = gid
                                pointsum['sc_row_ind'] = sc[gid]['row_ind']
                                pointsum['sc_col_ind'] = sc[gid]['col_ind']
                                summary[gid] = pointsum

        return summary

    @staticmethod
    def _parallel_summary(fpath_excl, fpath_gen, fpath_techmap,
                          resolution=64, gids=None, n_cores=None):
        """Get the supply curve points aggregation summary using futures.

        Parameters
        ----------
        fpath_excl : str
            Filepath to exclusions geotiff.
        fpath_gen : str
            Filepath to .h5 reV generation output results.
        fpath_techmap : str
            Filepath to tech mapping between exclusions and generation results
            (created using the reV TechMapping framework).
        resolution : int | None
            SC resolution, must be input in combination with gid. Prefered
            option is to use the row/col slices to define the SC point instead.
        gids : list | None
            List of gids to get summary for (can use to subset if running in
            parallel), or None for all gids in the SC extent.
        n_cores : int | None
            Number of cores to run summary on. None runs on all available cpus.

        Returns
        -------
        summary : dict
            Summary dictionary of the SC points keyed by SC point gid.
        """

        if n_cores is None:
            n_cores = os.cpu_count()

        if gids is None:
            with SupplyCurveExtent(fpath_excl, resolution=resolution) as sc:
                gids = np.array(range(len(sc)), dtype=np.uint32)

        chunks = np.array_split(gids, int(np.ceil(len(gids) / 1000)))

        logger.info('Running supply curve point aggregation for '
                    'points {} through {} at a resolution of {} '
                    'on {} cores in {} chunks.'
                    .format(gids[0], gids[-1], resolution, n_cores,
                            len(chunks)))

        n_finished = 0
        futures = []
        summary = {}

        with cf.ProcessPoolExecutor(max_workers=n_cores) as executor:

            # iterate through split executions, submitting each to worker
            for gid_set in chunks:
                # submit executions and append to futures list
                futures.append(executor.submit(Aggregation._serial_summary,
                                               fpath_excl, fpath_gen,
                                               fpath_techmap,
                                               resolution=resolution,
                                               gids=gid_set))
            # gather results
            for future in cf.as_completed(futures):
                n_finished += 1
                logger.info('Parallel aggregation futures collected: '
                            '{} out of {}'
                            .format(n_finished, len(chunks)))
                summary.update(future.result())

        return summary

    @classmethod
    def summary(cls, fpath_excl, fpath_gen, fpath_techmap, resolution=64,
                gids=None, n_cores=None, option='dataframe'):
        """Get the supply curve points aggregation summary.

        Parameters
        ----------
        fpath_excl : str
            Filepath to exclusions geotiff.
        fpath_gen : str
            Filepath to .h5 reV generation output results.
        fpath_techmap : str
            Filepath to tech mapping between exclusions and generation results
            The tech mapping module will be run if this file does not exist.
        resolution : int | None
            SC resolution, must be input in combination with gid. Prefered
            option is to use the row/col slices to define the SC point instead.
        gids : list | None
            List of gids to get summary for (can use to subset if running in
            parallel), or None for all gids in the SC extent.
        n_cores : int | None
            Number of cores to run summary on. 1 is serial, None is all
            available cpus.
        option : str
            Output dtype option (dict, dataframe).

        Returns
        -------
        summary : dict | DataFrame
            Summary of the SC points keyed by SC point gid.
        """

        if not os.path.exists(fpath_techmap):
            logger.info('Supply curve point aggregation could not find the '
                        'tech map file; running the TechMapping module '
                        'with output: {}'.format(fpath_techmap))
            TechMapping.run_map(fpath_excl, fpath_gen, fpath_techmap)

        if n_cores == 1:
            summary = cls._serial_summary(fpath_excl, fpath_gen, fpath_techmap,
                                          resolution=resolution, gids=gids)
        else:
            summary = cls._parallel_summary(fpath_excl, fpath_gen,
                                            fpath_techmap,
                                            resolution=resolution, gids=gids,
                                            n_cores=n_cores)
        if 'dataframe' in option.lower():
            summary = pd.DataFrame(summary).T
            summary = summary.set_index('sc_gid', drop=True).sort_index()

        return summary
