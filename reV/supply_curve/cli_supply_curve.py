# -*- coding: utf-8 -*-
"""
reV Supply Curve command line interface (cli).
"""
import os
import click
import logging
import pprint
import time

from reV.config.supply_curve_configs import SupplyCurveConfig
from reV.utilities.execution import SLURM
from reV.utilities.cli_dtypes import STR, INT
from reV.utilities.loggers import init_mult
from reV.utilities.utilities import dict_str_load
from reV.supply_curve.supply_curve import SupplyCurve
from reV.pipeline.status import Status

logger = logging.getLogger(__name__)


@click.command()
@click.option('--config_file', '-c', required=True,
              type=click.Path(exists=True),
              help='reV exclusions configuration json file.')
@click.option('-v', '--verbose', is_flag=True,
              help='Flag to turn on debug logging. Default is not verbose.')
@click.pass_context
def from_config(ctx, config_file, verbose):
    """Run reV supply curve compute from a config file."""
    name = ctx.obj['NAME']

    # Instantiate the config object
    config = SupplyCurveConfig(config_file)

    # take name from config if not default
    if config.name.lower() != 'rev':
        name = config.name

    # Enforce verbosity if logging level is specified in the config
    if config.log_level == logging.DEBUG:
        verbose = True

    # initialize loggers
    init_mult(name, config.logdir, modules=[__name__, 'reV.config',
                                            'reV.utilities'],
              verbose=verbose)

    # Initial log statements
    logger.info('Running reV supply curve from config '
                'file: "{}"'.format(config_file))
    logger.info('Target output directory: "{}"'.format(config.dirout))
    logger.info('Target logging directory: "{}"'.format(config.logdir))
    logger.debug('The full configuration input is as follows:\n{}'
                 .format(pprint.pformat(config, indent=4)))

    if config.execution_control.option == 'local':
        status = Status.retrieve_job_status(config.dirout, 'supply-curve',
                                            name)
        if status != 'successful':
            Status.add_job(
                config.dirout, 'supply-curve', name, replace=True,
                job_attrs={'hardware': 'local',
                           'fout': '{}.csv'.format(name),
                           'dirout': config.dirout})
            ctx.invoke(main, name, config.sc_points, config.trans_table,
                       config.fixed_charge_rate, config.sc_features,
                       config.transmission_costs, config.sort_on,
                       config.dirout, config.logdir,
                       config.simple, config.line_limited,
                       verbose)

    elif config.execution_control.option == 'eagle':

        ctx.obj['NAME'] = name
        ctx.obj['SC_POINTS'] = config.sc_points
        ctx.obj['TRANS_TABLE'] = config.trans_table
        ctx.obj['FIXED_CHARGE_RATE'] = config.fixed_charge_rate
        ctx.obj['SC_FEATURES'] = config.sc_features
        ctx.obj['TRANSMISSION_COSTS'] = config.transmission_costs
        ctx.obj['SORT_ON'] = config.sort_on
        ctx.obj['OUT_DIR'] = config.dirout
        ctx.obj['LOG_DIR'] = config.logdir
        ctx.obj['SIMPLE'] = config.simple
        ctx.obj['LINE_LIMITED'] = config.line_limited
        ctx.obj['VERBOSE'] = verbose

        ctx.invoke(eagle,
                   alloc=config.execution_control.alloc,
                   memory=config.execution_control.node_mem,
                   walltime=config.execution_control.walltime,
                   feature=config.execution_control.feature,
                   conda_env=config.execution_control.conda_env,
                   module=config.execution_control.module)


@click.group(invoke_without_command=True)
@click.option('--name', '-n', default='agg', type=STR,
              help='Job name. Default is "agg".')
@click.option('--sc_points', '-sc', type=STR, required=True,
              help='Supply curve point summary table (.csv or .json).')
@click.option('--trans_table', '-tt', type=STR, required=True,
              help='Supply curve transmission mapping table (.csv or .json).')
@click.option('--fixed_charge_rate', '-fcr', type=float, required=True,
              help='Fixed charge rate used to compute LCOT')
@click.option('--sc_features', '-scf', type=STR, default=None,
              help='Table containing additional supply curve features '
              '(.csv or .json)')
@click.option('--transmission_costs', '-tc', type=STR, default=None,
              help='Table or serialized dict of transmission cost inputs.')
@click.option('--sort_on', '-so', type=str, default='total_lcoe',
              help='The supply curve table column label to sort on. '
              'This determines the ordering of the SC buildout algorithm.')
@click.option('--out_dir', '-o', type=STR, default='./',
              help='Directory to save aggregation summary output.')
@click.option('--log_dir', '-ld', type=STR, default='./logs/',
              help='Directory to save aggregation logs.')
@click.option('-s', '--simple', is_flag=True,
              help='Flag to turn on simple supply curve calculation.')
@click.option('-ll', '--line_limited', is_flag=True,
              help='Flag to turn on line-limited substation capacity '
              'calculation (legacy methodology). Alternative is multi-line '
              'spread capacity.')
@click.option('-v', '--verbose', is_flag=True,
              help='Flag to turn on debug logging. Default is not verbose.')
@click.pass_context
def main(ctx, name, sc_points, trans_table, fixed_charge_rate, sc_features,
         transmission_costs, sort_on, out_dir, log_dir, simple, line_limited,
         verbose):
    """reV Supply Curve CLI."""

    ctx.ensure_object(dict)
    ctx.obj['NAME'] = name
    ctx.obj['SC_POINTS'] = sc_points
    ctx.obj['TRANS_TABLE'] = trans_table
    ctx.obj['FIXED_CHARGE_RATE'] = fixed_charge_rate
    ctx.obj['SC_FEATURES'] = sc_features
    ctx.obj['TRANSMISSION_COSTS'] = transmission_costs
    ctx.obj['SORT_ON'] = sort_on
    ctx.obj['OUT_DIR'] = out_dir
    ctx.obj['LOG_DIR'] = log_dir
    ctx.obj['SIMPLE'] = simple
    ctx.obj['LINE_LIMITED'] = line_limited
    ctx.obj['VERBOSE'] = verbose

    if ctx.invoked_subcommand is None:
        t0 = time.time()
        init_mult(name, log_dir, modules=[__name__, 'reV.supply_curve',
                                          'reV.handlers'],
                  verbose=verbose)

        if isinstance(transmission_costs, str):
            transmission_costs = dict_str_load(transmission_costs)

        if simple:
            sc_fun = SupplyCurve.simple
        else:
            sc_fun = SupplyCurve.full

        try:
            out = sc_fun(sc_points, trans_table, fixed_charge_rate,
                         sc_features=sc_features,
                         transmission_costs=transmission_costs,
                         line_limited=line_limited,
                         sort_on=sort_on)
        except Exception as e:
            logger.exception('Supply curve compute failed. Received the '
                             'following error:\n{}'.format(e))
            raise e

        fn_out = '{}.csv'.format(name)
        fpath_out = os.path.join(out_dir, fn_out)
        out.to_csv(fpath_out)

        runtime = (time.time() - t0) / 60
        logger.info('Supply curve complete. Time elapsed: {:.2f} min. '
                    'Target output dir: {}'.format(runtime, out_dir))

        finput = [sc_points, trans_table]
        if sc_features is not None:
            finput.append(sc_features)
        if transmission_costs is not None:
            finput.append(transmission_costs)

        # add job to reV status file.
        status = {'dirout': out_dir, 'fout': fn_out,
                  'job_status': 'successful',
                  'runtime': runtime,
                  'finput': finput}
        Status.make_job_file(out_dir, 'supply-curve', name, status)


def get_node_cmd(name, sc_points, trans_table, fixed_charge_rate, sc_features,
                 transmission_costs, sort_on, out_dir, log_dir, simple,
                 line_limited, verbose):
    """Get a CLI call command for the Supply Curve cli."""

    args = ('-n {name} '
            '-sc {sc_points} '
            '-tt {trans_table} '
            '-fcr {fixed_charge_rate} '
            '-scf {sc_features} '
            '-tc {transmission_costs} '
            '-so {sort_on} '
            '-o {out_dir} '
            '-ld {log_dir} '
            )

    args = args.format(name=SLURM.s(name),
                       sc_points=SLURM.s(sc_points),
                       trans_table=SLURM.s(trans_table),
                       fixed_charge_rate=SLURM.s(fixed_charge_rate),
                       sc_features=SLURM.s(sc_features),
                       transmission_costs=SLURM.s(transmission_costs),
                       sort_on=SLURM.s(sort_on),
                       out_dir=SLURM.s(out_dir),
                       log_dir=SLURM.s(log_dir),
                       )

    if simple:
        args += '-s '
    if line_limited:
        args += '-ll '
    if verbose:
        args += '-v '

    cmd = 'python -m reV.supply_curve.cli_supply_curve {}'.format(args)
    return cmd


@main.command()
@click.option('--alloc', '-a', required=True, type=STR,
              help='Eagle allocation account name.')
@click.option('--memory', '-mem', default=None, type=INT, help='Eagle node '
              'memory request in GB. Default is None')
@click.option('--walltime', '-wt', default=1.0, type=float,
              help='Eagle walltime request in hours. Default is 1.0')
@click.option('--feature', '-l', default=None, type=STR,
              help=('Additional flags for SLURM job. Format is "--qos=high" '
                    'or "--depend=[state:job_id]". Default is None.'))
@click.option('--conda_env', '-env', default=None, type=STR,
              help='Conda env to activate')
@click.option('--module', '-mod', default=None, type=STR,
              help='Module to load')
@click.option('--stdout_path', '-sout', default=None, type=STR,
              help='Subprocess standard output path. Default is in out_dir.')
@click.pass_context
def eagle(ctx, alloc, memory, walltime, feature, conda_env, module,
          stdout_path):
    """Eagle submission tool for reV supply curve aggregation."""

    name = ctx.obj['NAME']
    sc_points = ctx.obj['SC_POINTS']
    trans_table = ctx.obj['TRANS_TABLE']
    fixed_charge_rate = ctx.obj['FIXED_CHARGE_RATE']
    sc_features = ctx.obj['SC_FEATURES']
    transmission_costs = ctx.obj['TRANSMISSION_COSTS']
    simple = ctx.obj['SIMPLE']
    line_limited = ctx.obj['LINE_LIMITED']
    sort_on = ctx.obj['SORT_ON']
    out_dir = ctx.obj['OUT_DIR']
    log_dir = ctx.obj['LOG_DIR']
    verbose = ctx.obj['VERBOSE']

    if stdout_path is None:
        stdout_path = os.path.join(log_dir, 'stdout/')

    cmd = get_node_cmd(name, sc_points, trans_table, fixed_charge_rate,
                       sc_features, transmission_costs, sort_on,
                       out_dir, log_dir, simple, line_limited, verbose)

    status = Status.retrieve_job_status(out_dir, 'supply-curve', name)
    if status == 'successful':
        msg = ('Job "{}" is successful in status json found in "{}", '
               'not re-running.'
               .format(name, out_dir))
    else:
        logger.info('Running reV Supply Curve on Eagle with '
                    'node name "{}"'.format(name))
        slurm = SLURM(cmd, alloc=alloc, memory=memory,
                      walltime=walltime, feature=feature,
                      name=name, stdout_path=stdout_path,
                      conda_env=conda_env, module=module)
        if slurm.id:
            msg = ('Kicked off reV SC job "{}" (SLURM jobid #{}) on Eagle.'
                   .format(name, slurm.id))
            Status.add_job(
                out_dir, 'supply-curve', name, replace=True,
                job_attrs={'job_id': slurm.id, 'hardware': 'eagle',
                           'fout': '{}.csv'.format(name), 'dirout': out_dir})
        else:
            msg = ('Was unable to kick off reV SC job "{}". Please see the '
                   'stdout error messages'.format(name))
    click.echo(msg)
    logger.info(msg)


if __name__ == '__main__':
    try:
        main(obj={})
    except Exception:
        logger.exception('Error running reV Supply Curve CLI.')
        raise
