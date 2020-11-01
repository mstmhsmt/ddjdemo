#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
  A driver script for DD/Java container image

  Copyright 2018 Chiba Institute of Technology

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
'''

__author__ = 'Masatomo Hashimoto <m.hashimoto@stair.center>'

import os
import sys
import time
from datetime import datetime, timedelta
from subprocess import call, check_output
import re
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

IMAGE_NAME = 'codecontinuum/ddj:esecfse2018'

#

DDJ_USER = 'ddj'
DDJ_HOME = '/home/'+DDJ_USER
DDJ_SCRIPTS_DIR = DDJ_HOME+'/scripts'
DDJ_DATA_DIR = DDJ_HOME+'/data'
DDJ_MOUNT_POINT = '/mnt/results'

CONTAINER_CMD = 'docker'


### timezone
def get_TZ():
    TZ = None

    if time.timezone != 0:
        SIGN = '+' if time.timezone > 0 else '-'

        STDOFFSET = timedelta(seconds=-time.timezone)
        if time.daylight:
            DSTOFFSET = timedelta(seconds=-time.altzone)
        else:
            DSTOFFSET = STDOFFSET

        dt = datetime.now()
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, 0)
        stamp = time.mktime(tt)
        tt = time.localtime(stamp)

        isdst = tt.tm_isdst > 0

        tzname = None
        offset = 0

        if isdst:
            tzname = time.tzname[1]
            offset = DSTOFFSET
        else:
            tzname = time.tzname[0]
            offset = STDOFFSET

        TZ = '%s%s%s' % (tzname, SIGN, offset)

    return TZ

###

def get_image_name(devel=False):
    suffix = ''
    if devel and ':' not in IMAGE_NAME:
        suffix = ':devel'
    image = IMAGE_NAME+suffix
    return image

def prepare_dir(d, dry_run=False):
    path = os.path.abspath(d)
    if not dry_run:
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except Exception as e:
                print('"%s": faild to create: %s' % (path, e))
                path = None
    return path


def get_nparts(proj_id, container_cmd=CONTAINER_CMD):
    cmd = '%s run --rm -u %s %s %s/info.py --nparts' % (container_cmd,
                                                        DDJ_USER,
                                                        get_image_name(),
                                                        DDJ_SCRIPTS_DIR)

    cmd += ' ' + proj_id

    #print(cmd)

    try:
        out = int(check_output(cmd, shell=True,universal_newlines=True))
    except Exception as e:
        print('[WARNING] %s' % str(e))
        out = 1

    return out


def run_cmd(proj_id, container_cmd=CONTAINER_CMD, algo='dd', mem=8, staged=False,
            max_stmt_level=8, modified_stmt_rate_thresh=0.05,
            detach=True, rm=True, out_dir=None,
            plain=False, ex=None, part_number=None, dry_run=False, devel=False,
            decomp_only=False, shuffle=0, ignore_test_msg=False,
            optout=False, custom_split=False, greedy=False):

    if out_dir:
        if not prepare_dir(out_dir, dry_run=dry_run):
            exit(1)

    nparts = 1
    if ex == None:
        nparts = get_nparts(proj_id, container_cmd=container_cmd)

    for part in range(nparts):
        if part_number != None:
            if part != part_number:
                continue

        cmd = ''

        cmd += '%s run' % container_cmd

        if rm:
            cmd += ' --rm'

        cmd += ' -t'

        if detach:
            cmd += ' -d'

        tz = get_TZ()
        if tz:
            cmd += ' -e "TZ=%s"' % tz
        if DDJ_USER:
            cmd += ' -e "USER=%s"' % DDJ_USER
        if DDJ_HOME:
            cmd += ' -w %s' % DDJ_HOME

        cmd += ' -u %s' % DDJ_USER

        if nparts > 1:
            cmd += ' -e "DD_PART_NUM=%d"' % part

        if ex != None:
            cmd += ' -e "DD_EXAMPLE_NUM=%d"' % ex

        if not ignore_test_msg:
            cmd += ' -e "DD_INTERPRET_TEST_MSG=1"'

        guest_cmd_name = None
        container_name = ''
        if devel:
            container_name = 'x-'

        _proj_id = proj_id

        if decomp_only:
            if proj_id.endswith('_d4j'):
                _proj_id = re.sub(r'_d4j$', '', proj_id)
                guest_cmd_name = 'decomp_only_d4j.sh'
                container_name += 'd4j-%s' % _proj_id

            elif proj_id.endswith('_ddj'):
                _proj_id = re.sub(r'_ddj$', '', proj_id)
                guest_cmd_name = 'decomp_only_ddj.sh'
                container_name += 'ddj-%s' % _proj_id

            else:
                print('invalid project ID: "%s"' % proj_id)
                exit(1)
        else:
            if proj_id.endswith('_d4j'):
                _proj_id = re.sub(r'_d4j$', '', proj_id)
                guest_cmd_name = 'batch_%sd4j.sh' % ('p_' if plain else '')
                container_name += 'd4j-%s%s-' % (('plain-' if plain else ''), _proj_id)

            elif proj_id.endswith('_ddj'):
                _proj_id = re.sub(r'_ddj$', '', proj_id)
                guest_cmd_name = 'batch_%sddj.sh' % ('p_' if plain else '')
                container_name += 'ddj-%s%s-' % (('plain-' if plain else ''), _proj_id)

            else:
                print('invalid project ID: "%s"' % proj_id)
                exit(1)

        guest_cmd_path = '%s/%s' % (DDJ_SCRIPTS_DIR, guest_cmd_name)

        guest_cmd = guest_cmd_path

        if not decomp_only:
            guest_cmd += ' -a %s' % (algo if plain else algo.upper())

        if not plain:
            guest_cmd += ' -m %d' % mem

        if not decomp_only and staged and not plain:
            guest_cmd += ' -s -l %d -t %f' % (max_stmt_level, modified_stmt_rate_thresh)
            container_name += 's%d' % max_stmt_level

        if shuffle:
            guest_cmd += ' -u %d' % shuffle

        if optout and not plain:
            guest_cmd += ' -x'

        if custom_split and not plain:
            guest_cmd += ' -c'

        if greedy:
            guest_cmd += ' -g'

        guest_cmd += ' %s' % _proj_id

        if decomp_only:
            cp_cmd = 'cp %s/%s.decomp.log %s/' % (DDJ_DATA_DIR, _proj_id, DDJ_MOUNT_POINT)
        else:
            cp_cmd = 'cp %s/DD/%s.log %s/' % (DDJ_DATA_DIR, proj_id, DDJ_MOUNT_POINT)

        guest_cmd += ' || %s' % cp_cmd
        guest_cmd = '(time %s) >& %s/log' % (guest_cmd, DDJ_MOUNT_POINT)

        if not decomp_only:
            container_name += algo

        if not plain:
            container_name += '-%dG' % mem

        if shuffle:
            container_name += '-u%d' % shuffle

        if optout and not plain:
            container_name += '-o'

        if custom_split and not plain:
            container_name += '-c'

        if greedy:
            container_name += '-g'

        if ignore_test_msg:
            container_name += '-i'

        if nparts > 1:
            container_name += '-%d' % part

        if ex != None:
            container_name += '-ex%d' % ex

        if out_dir:
            path = prepare_dir(os.path.join(out_dir, container_name), dry_run=dry_run)
            cmd += ' -v %s:%s' % (path, DDJ_MOUNT_POINT)

        cmd += ' --name %s' % container_name
        cmd += ' %s' % get_image_name(devel=devel)
        cmd += ' /bin/bash -l -c "%s"' % guest_cmd

        print(cmd)

        if not dry_run:
            try:
                call(cmd, shell=True)
                time.sleep(3)

            except (KeyboardInterrupt, SystemExit):
                print('interrupted.')

            except OSError as e:
                print('execution failed: %s' % e)
            

def list_projs(args):
    cmd = '%s run --rm -u %s %s %s/info.py' % (args.container_cmd,
                                               DDJ_USER,
                                               get_image_name(),
                                               DDJ_SCRIPTS_DIR)
    if args.projs:
        cmd += ' ' + ' '.join(args.projs)

    print(cmd)

    call(cmd, shell=True)

def update(args):
    cmd = '%s pull %s' % (args.container_cmd, get_image_name(devel=args.devel))
    print(cmd)
    if not args.dry_run:
        try:
            call(cmd, shell=True)
        except OSError as e:
            print('execution failed: %s' % e)

def run(args):
    if args.ex == None and args.part == None and not args.all:
        print('Specify example (-e N) or part (-p N).')
        print('Use "--all" option if you want to process all examples')
    else:
        run_cmd(args.proj_id, container_cmd=args.container_cmd,
                algo=args.algo, mem=args.mem, staged=args.staged,
                max_stmt_level=args.max_stmt_level,
                modified_stmt_rate_thresh=args.modified_stmt_rate_thresh,
                detach=False, rm=(not args.keep), out_dir=args.out_dir,
                plain=args.plain, ex=args.ex, part_number=args.part,
                dry_run=args.dry_run, devel=args.devel,
                decomp_only=args.decomp_only, shuffle=args.shuffle,
                ignore_test_msg=args.ignore_test_msg,
                optout=args.optout, custom_split=args.custom_split, greedy=args.greedy)

def main():
    parser = ArgumentParser(description='DD/Java Demo Driver',
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-c', '--container-command', dest='container_cmd', metavar='CMD',
                        help='specify container command', default=CONTAINER_CMD)

    subparsers = parser.add_subparsers(title='subcommands')

    parser_list = subparsers.add_parser('list',
                                        description='List projects',
                                        formatter_class=ArgumentDefaultsHelpFormatter)

    parser_list.add_argument('projs', type=str, nargs='*', metavar='PROJ_ID')

    parser_list.set_defaults(func=list_projs)

    parser_update = subparsers.add_parser('update',
                                          description='Update docker image of DD/Java demo',
                                          formatter_class=ArgumentDefaultsHelpFormatter)

    parser_update.set_defaults(func=update)

    parser_run = subparsers.add_parser('run',
                                       description='Run a demo',
                                       formatter_class=ArgumentDefaultsHelpFormatter)

    parser_run.add_argument('--plain', dest='plain', action='store_true',
                            help='use text diff/patch instead of AST diff/patch')

    parser_run.add_argument('-a', '--algo', dest='algo', metavar='ALGO',
                            choices=['dd', 'ddmin'],
                            help='specify DD algorithm', default='ddmin')

    parser_run.add_argument('-m', '--mem', dest='mem', metavar='GB', type=int,
                            choices=[8, 16, 32, 48, 64],
                            help='specify available memory (GB)', default=8)

    parser_run.add_argument('-s', '--staged', dest='staged', action='store_true',
                            help='enable staged DD')

    parser_run.add_argument('--max-stmt-level', dest='max_stmt_level', default=8,
                            metavar='N', type=int, help='grouping statements at the level up to N')

    parser_run.add_argument('--modified-stmt-rate-thresh', dest='modified_stmt_rate_thresh',
                            default=0.05,
                            metavar='R', type=float,
                            help='suppress level 1+ statement grouping when modified statement rate is less than R')

    parser_run.add_argument('--shuffle', dest='shuffle', type=int, metavar='N', default=0,
                            help='shuffle delta components N times')

    parser_run.add_argument('--optout', dest='optout', action='store_true',
                            help='opt out delta components')

    # parser_run.add_argument('--custom-split', dest='custom_split', action='store_true',
    #                         help='enable custom split')

    parser_run.add_argument('--simple-split', dest='custom_split', action='store_false',
                            help='disable custom split')

    parser_run.add_argument('--greedy', dest='greedy', action='store_true',
                            help='try to find multiple solutions')

    parser_run.add_argument('-e', '--example', dest='ex', metavar='N', type=int,
                            help='specify example number', default=None)

    parser_run.add_argument('-p', '--part', dest='part', metavar='N', type=int,
                            help='specify part number', default=None)

    parser_run.add_argument('--all', dest='all', action='store_true',
                            help='process all examples')

    parser_run.add_argument('-k', '--keep', dest='keep', action='store_true',
                            help='keep container')

    # parser_run.add_argument('-f', '--foreground', dest='fg', action='store_true',
    #                         help='run in foreground')

    parser_run.add_argument('-o', '--out-dir', dest='out_dir', metavar='DIR',
                            help='specify root directory for the results', default='DDX')

    parser_run.add_argument('-n', '--dry-run', dest='dry_run', action='store_true',
                            help='only print commands')

    parser_run.add_argument('-x', '--experimental', dest='devel', action='store_true',
                            help='use experimental image')

    parser_run.add_argument('--decomp-only', dest='decomp_only', action='store_true',
                            help='test delta decomposition')

    parser_run.add_argument('-i', '--ignore-test-msg', dest='ignore_test_msg', action='store_true',
                            help='ignore test messages')

    parser_run.add_argument('proj_id', type=str, metavar='PROJ_ID',
                            help='project ID')

    parser_run.set_defaults(func=run)


    args = parser.parse_args()

    args.func(args)


if __name__ == '__main__':
    main()
