"""Exercise the actual resolver functions without triggering full re-ingestion."""
import ast,collections,json,pathlib,re,tempfile
source=pathlib.Path(__file__).with_name('inventory.py').read_text(encoding='utf8');tree=ast.parse(source)
module=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['project_guid_index','resolve']],type_ignores=[])
with tempfile.TemporaryDirectory(prefix='source-resolution-') as directory:
 root=pathlib.Path(directory);asset=root/'NewProject/Assets/NewFolder/icon.png';asset.parent.mkdir(parents=True);asset.write_bytes(b'fixture')
 meta=pathlib.Path(str(asset)+'.meta');guid='1234567890abcdef1234567890abcdef';meta.write_text('guid: '+guid)
 env={'pathlib':pathlib,'re':re,'collections':collections,'guid_indexes':{},'project_files':{'P':[asset,meta]},'name_index':{'P':{'icon.png':[asset]}}}
 exec(compile(module,'inventory-resolver','exec'),env)
 original=str(root/'OldProject/Assets/OldFolder/icon.png')
 found,method,_=env['resolve']({'project':'P','absolute_path':original,'guid':guid});assert found==asset and method=='unity_guid'
 found,method,_=env['resolve']({'project':'P','absolute_path':str(asset)});assert found==asset and method=='original_path'
 found,method,_=env['resolve']({'project':'P','absolute_path':str(root/'Old/Assets/missing.png')});assert found is None and method=='missing'
 copy=root/'NewProject/Assets/Other/icon.png';copy.parent.mkdir();copy.write_bytes(b'fixture2');copy_meta=pathlib.Path(str(copy)+'.meta');copy_meta.write_text('guid: '+guid);env['project_files']['P']+=[copy,copy_meta];env['guid_indexes'].clear()
 found,method,candidates=env['resolve']({'project':'P','absolute_path':original,'guid':guid});assert found is None and method=='ambiguous_guid' and len(candidates)==2
report={'passed':True,'checks':['same GUID resolves moved file','existing path preserved','missing file remains missing','duplicate GUID rejected as ambiguous']}
pathlib.Path('E:/AI/output/asset-library-v2/data/source-resolver-validation.json').write_text(json.dumps(report,indent=2));print('Source resolver: 4 checks PASS')
