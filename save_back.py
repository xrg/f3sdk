#!/usr/bin/python
# -*- coding: utf-8 -*-
##############################################################################
#
#    F3, Open Source Management Solution
#    Copyright (C) 2013 P. Christeas <xrg@hellug.gr>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp_libclient import rpc
from openerp_libclient.extra import options
import logging
import sys
import optparse
import os
import os.path
from lxml import etree
from collections import defaultdict
from itertools import chain


def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "Iteration options")
    pgroup.add_option('--force', default=False, action='store_true',
            help="Continue on errors")
    pgroup.add_option('--dry-run', default=False, action='store_true',
            help="Just print the results")

    pgroup.add_option("--addons-dir", help="Directory containing these addons")
    pgroup.add_option('--encoding', help="Output encoding")
    parser.add_option_group(pgroup)
    #pgroup.add_option('--limit', type=int, help="Limit of forms to import")

help_usage = """Download contents of some record field into regular files
"""
options.allow_include = 3
options._path_options.append('addons_dir')

options.init(usage=help_usage, options_prepare=custom_options,
        have_args=True, config_section=(),
        config='~/.openerp/save_back.conf',
        defaults={'encoding': 'utf-8', })

log = logging.getLogger('main')

log.info("Init. Connecting to F3 server...")
rpc.openSession(**options.connect_dsn)
if not rpc.login():
    raise Exception("Could not login!")

# context = {'lang': 'el_GR', }
context = {}

class ModuleSaver(object):
    def __init__(self, module, addons_dir):
        self.module = module
        self.addons_dir = addons_dir
        self.nfiles = 0
        self.nfsaves = 0
        self.module_basedir = os.path.join(options.opts.addons_dir, module)
        self._ready = False
        self.desc = {}
        self._proxies = {}

    def init(self):
        mfname = '?'
        mfname = os.path.join(self.module_basedir, '__openerp__.py')
        fp = open(mfname, 'rb')
        try:
            self.desc = eval(fp.read(), {}, {})
        finally:
            fp.close()
        self._imd_obj = self.get_proxy('ir.model.data')
        self._ready = True

    def get_proxy(self, model):
        if model not in self._proxies:
            self._proxies[model] = rpc.RpcProxy(model)
        return self._proxies[model]

    def _process_file(self, fname, dry_run=True):
        self.nfiles += 1
        ext = fname.rsplit('.',1)[-1].lower()
        fn = getattr(self, '_process_file_'+ ext, None)
        if fn is not None:
            self.nfsaves += 1
            fp = False
            log.debug("Processing \"%s\" as %s", fname, ext)
            try:
                fparts = fname.split('/')
                fp = open(os.path.join(self.module_basedir, *fparts), 'rb')
                ret = fn(fp, dry_run)
                if ret is not None:
                    fp.close()
                    fp = open(os.path.join(self.module_basedir, *fparts), 'wb')
                    ret(fp)
                    log.info("Changes saved to: %s", fname)
            finally:
                if fp:
                    fp.close()
        else:
            log.debug("Skipping %s, unknown extension", fname)

    def process_normal(self, dry_run=True):
        for key in ('init_xml', 'update_xml', 'data'):
            for dfile in self.desc.get(key, []):
                self._process_file(dfile, dry_run)

    def process_demo(self, dry_run=True):
        for key in ('demo', 'demo_xml'):
            for dfile in self.desc.get(key, []):
                self._process_file(dfile, dry_run)

    def _process_file_xml(self, fp, dry_run=True):

        doc = etree.parse(fp) # , parser=self._xml_parser)
        root = doc.getroot()
        xml_dirty = False
        if root.tag != 'openerp':
            self.logger.error("Mismatch xml format")
            raise Exception( "Mismatch xml format: only openerp is allowed as root tag" )

        # First pass: collect the IMD ids for each model
        model_imds = defaultdict(list)

        for n in root.findall('./data'):
            for rec in n:
                if isinstance(rec, etree.CommentBase):
                    continue
                if rec.tag == 'record':
                    model_imds[rec.get('model')].append(rec.get('id'))

        imds_data = {}
        # Read all ir.model.data records for our file and group by IMD id
        for imd_rec in self._imd_obj.search_read([('module', '=', self.module),\
                        ('name', 'in', list(chain.from_iterable(model_imds.values())))], context=context):
            imds_data[imd_rec['name']] = imd_rec

        model_ids = defaultdict(list)
        # Match ir.model.data entries against our <record> elements
        for model, imdids in model_imds.items():
            for imd in imdids:
                if imd not in imds_data:
                    log.warning("Record \"%s.%s\" for model %s not in this db!",
                                    module, imd, model)
                elif imds_data[imd]['model'] != model:
                    log.error("Model mismatch for \"%s.%s\" xml=\"%s\", db=\"%s\"",
                                    module, imd, model, imds_data[imd]['model'])
                    imds_data.pop(imd)
                else:
                    model_ids[model].append(imds_data[imd]['res_id'])

        # Read modification dates and keep records that have changed
        dirty_records = defaultdict(dict)
        for model, ids in model_ids.items():
            proxy = self.get_proxy(model)
            model_dates = {}
            for res in proxy.perm_read(ids, details=False):
                model_dates[res['id']] = res['write_date'] or res['create_date']

            for imd in model_imds[model]:
                if imd not in imds_data:
                    continue
                if imds_data[imd]['res_id'] not in model_dates:
                    continue
                if (imds_data[imd]['date_update'] or imds_data[imd]['date_init']) \
                        < model_dates[imds_data[imd]['res_id']]:
                    dirty_records[model][imd] = imds_data[imd]['res_id']
                else:
                    dirty_records[model][imd] = False
            del model_dates

        # Second pass, scan <record>s again and update them
        for n in root.findall('./data'):
            for rec in n:
                if isinstance(rec, etree.CommentBase):
                    continue
                if rec.tag == 'record':
                    dirty_id = dirty_records[rec.get('model')].get(rec.get('id'), False)
                    if not dirty_id:
                        continue
                    model = rec.get('model')
                    log.debug("Record %s: %s may need an update", model, rec.get('id'))
                    proxy = self.get_proxy(model)
                    log.debug("Reading: %s[%s]", model, dirty_id)
                    data = proxy.read(dirty_id, context=context)
                    if not data:
                        log.warning("No data found for %s[%s], skipping", model, dirty_id)
                        continue
                    # see if real record is newer than imd_rec
                    # TODO general fields
                    for field in rec.findall('./field'):
                        field_name = field.get('name')
                        if not field_name:
                            log.warning('Strange, field w/o "name" attribute at %s:%s', fp.name, rec.sourceline or '?')
                            continue
                        if field.get('search'):
                            pass
                        elif field.get('eval'):
                            pass
                        elif field.get('ref'):
                            pass
                        elif field.get('file'):
                            fname = field.get('file')
                            rfp = False
                            if not data[field_name]:
                                log.debug("Field %s.[%s].%s changed to false, removing",
                                        model, rec.get('id'), field_name)
                                field.attrib.pop('file')
                                xml_dirty = True
                            rfname = os.path.join(self.module_basedir, fname)
                            if dry_run:
                                log.debug("New data should be written to: %s", rfname)
                            else:
                                try:
                                    rfp = open(rfname, 'wb')
                                    rfp.write(data[field_name])
                                    log.info("Data written to: %s", rfname)
                                finally:
                                    if rfp:
                                        rfp.close()
                        else:
                            if (field.text != (data[field_name] or '')):
                                field.text = data[field_name] or ''
                                xml_dirty = True
                else:
                    pass
                    # TODO tags: record act_window url workflow menuitem

        if xml_dirty and dry_run:
            log.info("XML dirty: %s, but no write", fp.name)
        elif xml_dirty:
            log.info("XML dirty, saving changes to %s", fp.name)
            return lambda fp: doc.write(fp, encoding='utf-8')
        return None
try:
    nmodules = 0
    nfailures = 0
    for module in options.args:
        log.debug("Trying module %s", module)
        ms = ModuleSaver(module, options.opts.addons_dir)
        try:
            ms.init()
            log.debug("Processing module %s: %s", module, ms.desc['name'])
            nmodules += 1
            ms.process_normal(options.opts.dry_run)
            ms.process_demo(options.opts.dry_run)
            log.info("Finished %s: %d files, %d saved", module, ms.nfiles, ms.nfsaves)
        except Exception:
            log.exception("Cannot process %s:", module)
            nfailures += 1
            if not options.opts.force:
                raise

except Exception:
    log.exception("Fail: ")
    sys.exit(3)

#eof