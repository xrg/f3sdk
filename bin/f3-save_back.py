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
#import re
from lxml import etree
from collections import defaultdict
from itertools import chain
import csv


def custom_options(parser):
    assert isinstance(parser, optparse.OptionParser)

    pgroup = optparse.OptionGroup(parser, "Iteration options")
    pgroup.add_option('--force', default=False, action='store_true',
            help="Continue on errors")
    pgroup.add_option('--dry-run', default=False, action='store_true',
            help="Just print the results")
    pgroup.add_option('--touch', default=False, action='store_true',
            help="Update ir.model.data records with save date")

    pgroup.add_option("--addons-dir", help="Directory containing these addons")
    pgroup.add_option('--encoding', help="Output encoding")
    parser.add_option_group(pgroup)
    #pgroup.add_option('--limit', type=int, help="Limit of forms to import")

help_usage = """Download contents of some record field into regular files
"""
options.allow_include = 3
options._path_options.append('addons_dir')

options.init(usage=help_usage, options_prepare=custom_options,
        config_section=(),
        config='~/.openerp/save_back.conf',
        defaults={'encoding': 'utf-8', })

log = logging.getLogger('main')

log.info("Init. Connecting to F3 server...")
rpc.openSession(**options.connect_dsn)
if not rpc.login():
    raise Exception("Could not login!")

# context = {'lang': 'el_GR', }
context = {}

class UstrFeeder(object):
    """ Wraps a file-like object with UTF-8 decoder
    """
    __slots__ = ('_fp', '_encoding')

    def __init__(self, fp, encoding):
        self._fp = fp
        self._encoding = encoding

    def _ustr(self, sstr):
        if sstr:
            return unicode(sstr, self._encoding)
        else:
            return ''

    def next(self):
        return map(self._ustr, self._fp.next())

    def __getattr__(self, name):
        return getattr(self._fp, name)

    def __iter__(self):
        return self

class ModuleSaver(object):
    # _ws_re = re.compile(r'\s+')
    def __init__(self, module, addons_dir):
        self.module = module
        self.addons_dir = addons_dir
        self.nfiles = 0
        self.nfsaves = 0
        self.module_basedir = os.path.join(options.opts.addons_dir, module)
        self._ready = False
        self.desc = {}
        self._proxies = {}
        self._model_fields = defaultdict(dict)
        self._do_touch = options.opts.touch

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

    def get_model_field(self, model, field):
        if field not in self._model_fields[model]:
            res = self.get_proxy(model).fields_get([field,])
            self._model_fields[model].update(res)
        return self._model_fields[model][field]

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
                                    self.module, imd, model)
                elif imds_data[imd]['model'] != model:
                    log.error("Model mismatch for \"%s.%s\" xml=\"%s\", db=\"%s\"",
                                    self.module, imd, model, imds_data[imd]['model'])
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
                    dirty_records[model][imd] = imds_data[imd]['res_id'], model_dates[imds_data[imd]['res_id']]
                else:
                    dirty_records[model][imd] = False, False
            del model_dates

        # Second pass, scan <record>s again and update them
        for n in root.findall('./data'):
            for rec in n:
                if isinstance(rec, etree.CommentBase):
                    continue
                if rec.tag == 'record':
                    dirty_id, rec_date = dirty_records[rec.get('model')].get(rec.get('id'), (False, False))
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
                            model_field = self.get_model_field(model, field_name)
                            if model_field['type'] in ('integer', 'char', 'float', 'boolean'):
                                if field.get('eval') != repr(data[field_name]):
                                    field.attrib['eval'] = repr(data[field_name])
                                    xml_dirty = True
                            else:
                                log.warning("Cannot handle eval of: %s.%s[%s]", model, field_name, model_field['type'])
                        elif field.get('ref'):
                            model_field = self.get_model_field(model, field_name)
                            log.debug("Ref %s into %s: %s", field.get('ref'), field_name, data[field_name])
                            if model_field['type'] == 'many2one':
                                assert model_field['relation'], "No relation in %r" % model_field
                                if data[field_name]:
                                    refs = self._imd_obj.get_rev_ref(model_field['relation'], data[field_name][0])
                                    assert refs[0] == data[field_name][0], "Garbage came: %r" % refs
                                    found_ref = False
                                    if refs[1]:
                                        for r in refs[1]:
                                            # try to locate a ref in our own modulw
                                            if r.startswith(self.module + '.'):
                                                found_ref = r[len(self.module)+1:]
                                                break
                                        else:
                                            # pick first ref available
                                            found_ref = refs[1][0]
                                    if not found_ref:
                                        log.warning("Record %s.#%d \"%s\" does not have an XML ID, please tag it!",
                                                model_field['relation'], data[field_name][0], data[field_name][1])
                                        # don't set dirty flag!
                                    elif found_ref != field.get('ref'):
                                        field.attrib['ref'] = found_ref
                                        xml_dirty = True
                                else:
                                    # no data, remove ref
                                    field.attrib.pop('ref')
                                    xml_dirty = True
                            else:
                                raise NotImplementedError("Cannot resolve refs for %s" % model_field['type'])
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
                                    dstr = data[field_name]
                                    if isinstance(dstr, unicode):
                                        dstr = dstr.encode('utf-8')
                                    rfp.write(dstr)
                                    log.info("Data written to: %s", rfname)
                                finally:
                                    if rfp:
                                        rfp.close()
                        elif field.get('type', False) == 'xml':
                            try:
                                newxml = etree.fromstring(data[field_name] or '')
                                children = list(field)
                                if newxml.tag == 'data' and not (data[field_name] or '')[:30].strip().startswith('<data>'):
                                    # it was multiple elements, that etree parser wrapped with a <data> one.
                                    new_elems = list(newxml)
                                    last_tail = None
                                    nc = None
                                    for c in children:
                                        last_tail = c.tail
                                        if not new_elems:
                                            field.remove(c)
                                            continue
                                        nc = new_elems.pop(0)
                                        if (nc != c):
                                            field.replace(c, nc)
                                            xml_dirty = True
                                    for nc in new_elems:
                                        field.append(nc)
                                        xml_dirty = True
                                    if last_tail and nc:
                                        nc.tail = last_tail
                                elif children:
                                    if (newxml != children[0]):
                                        newxml.tail = children[0].tail
                                        field.replace(children[0], newxml)
                                        xml_dirty = True

                                    # then, remove all spurious children
                                    i = len(children) - 1
                                    while i > 0:
                                        field.remove(children[i])
                                        i -= 1
                                else:
                                    field.append(newxml)
                                    # try to align at the same indent as parent elem:
                                    if field.text.endswith('    '):
                                        newxml.tail = field.text[:-4]
                                    else:
                                        newxml.tail = field.text
                                    xml_dirty = True
                            except Exception, e:
                                log.warning("Failed to do type=xml comparison:", exc_info=True)
                                field.text = data[field_name] or ''
                                xml_dirty = True
                        else:
                            if isinstance(data[field_name], (int, float)):
                                # In case it's a number allow cast to text, just to preserve XML
                                # but if it is different value, convert to eval=".."
                                txt = repr(data[field_name])
                                if field.text != txt:
                                    field.text = ''
                                    field.attrib['eval'] = txt
                                    xml_dirty = True
                            else:
                                assert isinstance(data[field_name], basestring), "%s: %r" %(field_name, data[field_name])
                                if (field.text != (data[field_name] or '')):
                                    field.text = data[field_name] or ''
                                    xml_dirty = True
                    if self._do_touch and not dry_run:
                        self._imd_obj.write(imds_data[rec.get('id')]['id'], {'date_update': rec_date}, context=context)
                else:
                    pass
                    # TODO tags: record act_window url workflow menuitem

        if xml_dirty and dry_run:
            log.info("XML dirty: %s, but no write", fp.name)
        elif xml_dirty:
            log.info("XML dirty, saving changes to %s", fp.name)
            return lambda fp: doc.write(fp, encoding='utf-8')
        return None

    def _process_file_csv(self, fp, dry_run=True):
        if not fp.name:
            raise AttributeError("CSV files must have a filename!")
        model_name = os.path.basename(fp.name)[:-4]
        log.debug("CSV uses model: %s", model_name)
        
        reader = UstrFeeder(csv.reader(fp), 'utf-8')
        headers = reader.next()
        if not headers:
            raise RuntimeError("No CSV headers line!")

        if "id" not in headers:
            raise RuntimeError("CSV must contain an 'id' column, for reference")

        proxy = self.get_proxy(model_name)
        model_fields = proxy.fields_get()

        all_data = list(reader) # read all remaining lines!

        id_pos = headers.index('id')
        imds = defaultdict(dict)
        for i, d in enumerate(all_data):
            if not d:
                continue
            imds[d[id_pos]]['csv_line'] = i

        # Read all ir.model.data records for our file and group by IMD id
        for imd_rec in self._imd_obj.search_read([('module', '=', self.module),
                        ('name', 'in', imds.keys())], context=context):
            if imd_rec['model'] != model_name:
                log.error("Model mismatch for \"%s.%s\" xml=\"%s\", db=\"%s\"",
                                self.module, imd_rec['name'], model_name, imd_rec['model'])
            imd_d = imds[imd_rec['name']]
            imd_d['id'] = imd_rec.pop('res_id')
            imd_d['imd'] = imd_rec

        # Match ir.model.data entries against our <record> elements
        model_ids = []
        for imd, mdic in imds.items():
            if 'id' in mdic:
                model_ids.append(mdic['id'])
            else:
                log.warning("Record \"%s.%s\" for model %s not in this db!",
                                self.module, imd, model_name)

        # Read modification dates and keep records that have changed
        model_dates = {}
        for res in proxy.perm_read(model_ids, details=False):
            model_dates[res['id']] = res['write_date'] or res['create_date']

        dirty_records = []
        for imd in imds.values():
            if ('id' in imd) and (imd['id'] in model_dates):
                if (imd['imd']['date_update'] or imd['imd']['date_init']) < model_dates[imd['id']]:
                    dirty_records.append(imd['id'])
                    imd['res_date'] = model_dates[imd['id']]
        del model_dates

        if not dirty_records:
            log.debug("CSV has no changes")
            return
        res_d = proxy.export_data(dirty_records, headers)

        header_ids = []
        bool_fields = []
        for i,h in enumerate(headers):
            if h == 'id' or h.endswith(':id'):
                header_ids.append(i)
            elif model_fields.get(h, {}).get('type',False) == 'boolean':
                bool_fields.append(i)

        mod_prefix = self.module + '.'
        dirty_imds = []
        for line in res_d.get('datas',[]):
            for i in header_ids:
                if i <= len(line) and line[i] and line[i].startswith(mod_prefix):
                    line[i] = line[i][len(mod_prefix):]

            for i in bool_fields:
                # Note: here we map "None" to False!
                if i <= len(line):
                    if line[i] and line[i] != 'False':
                        line[i] = '1'
                    else:
                        line[i] = '0'

            imd = imds[line[id_pos]]
            if all_data[imd['csv_line']] != line:
                all_data[imd['csv_line']] = line
                dirty_imds.append(line[id_pos])

        def __to_utf8(ss):
            if isinstance(ss, unicode):
                return ss.encode('utf-8')
            else:
                return ss

        def __save_csv(fp):
            writer = csv.writer(fp)
            writer.writerow(map(__to_utf8, headers))
            for line in all_data:
                writer.writerow(map(__to_utf8, line))

            for d in dirty_imds:
                imd = imds[d]
                self._imd_obj.write(imd['imd']['id'], 
                        {'date_update': imd['res_date']}, context=context)
            return True

        if dirty_imds and dry_run:
            log.info("CSV dirty: %s, but no write. IMDs changed: %r", fp.name, dirty_imds)
        elif dirty_imds:
            log.info("CSV dirty, saving changes to %s", fp.name)
            return __save_csv
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