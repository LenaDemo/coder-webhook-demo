"""Build a local image from the official, checksum-verified Coder binary."""
import hashlib
import platform
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
build=ROOT/".state/control-build"
build.mkdir(parents=True,exist_ok=True)
arch={"arm64":"arm64","aarch64":"arm64","x86_64":"amd64","amd64":"amd64"}[platform.machine()]
version="2.39.0"
base=f"https://github.com/coder/coder/releases/download/v{version}/"
name=f"coder_{version}_linux_{arch}.tar.gz"
checks=urllib.request.urlopen(base+f"coder_{version}_checksums.txt",timeout=45).read().decode()
expected=next(line.split()[0] for line in checks.splitlines() if line.split()[-1]==name)
archive=build/name
if not archive.exists() or hashlib.file_digest(archive.open("rb"),"sha256").hexdigest()!=expected:
    partial=archive.with_suffix(".partial")
    with urllib.request.urlopen(base+name,timeout=60) as response, partial.open("wb") as output:
        shutil.copyfileobj(response,output)
    if hashlib.file_digest(partial.open("rb"),"sha256").hexdigest()!=expected:
        raise SystemExit("Official Coder archive checksum did not match.")
    partial.replace(archive)
with tarfile.open(archive) as tar:
    members=[m for m in tar.getmembers() if m.isfile() and (m.name=="coder" or m.name.endswith("/coder"))]
    if len(members)!=1:raise SystemExit("Unexpected Coder archive contents.")
    (build/"coder").write_bytes(tar.extractfile(members[0]).read())
(build/"coder").chmod(0o755)
print("Coder binary verified against the official release checksum.",flush=True)
subprocess.run(["docker","build","-t","lena-coder-control:2.39.0","-f",
                str(ROOT/"coder/control.Dockerfile"),str(build)],check=True)
