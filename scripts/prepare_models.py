"""Build-machine only: pin upstream source and copy checkpoints into installer."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'model-assets'
VENDOR=ROOT/'vendor'

def main():
    VENDOR.mkdir(exist_ok=True)
    checkout=VENDOR/'Kronos'
    if not checkout.exists():subprocess.run(['git','clone','https://github.com/shiyu-coder/Kronos.git',str(checkout)],check=True)
    subprocess.run(['git','-C',str(checkout),'checkout','67b630e67f6a18c9e9be918d9b4337c960db1e9a'],check=True)
    # Pin tested source; checkpoint hashes retained in manifest.
    revision=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
    packages=ROOT/'src'/'model'
    if packages.exists():shutil.rmtree(packages)
    shutil.copytree(checkout/'model',packages)
    ASSETS.mkdir(exist_ok=True)
    manifest={'kronos_source':revision,'models':{}}
    for repo,name in [('NeoQuasar/Kronos-small','kronos'),('NeoQuasar/Kronos-Tokenizer-base','tokenizer'),('google/timesfm-2.5-200m-pytorch','timesfm')]:
        folder=Path(snapshot_download(repo_id=repo,local_dir=str(ASSETS/name),allow_patterns=['config.json','model.safetensors','README.md','LICENSE*']))
        for temporary in folder.glob('.model.safetensors*'):
            temporary.unlink()
        hashes={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file() and '.cache' not in p.parts}
        manifest['models'][name]={'repo':repo,'sha256':hashes}
        shutil.rmtree(folder/'.cache',ignore_errors=True)
    licenses=ASSETS/'licenses';licenses.mkdir(exist_ok=True)
    for name in ('LICENSE','README.md'):
        if (checkout/name).exists():shutil.copy2(checkout/name,licenses/('Kronos-'+name))
    (ASSETS/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'kronos_source':revision,'assets':str(ASSETS)}))

if __name__=='__main__':main()
