"""Start or switch this project's local 256K service; only owned processes can be stopped."""
import argparse, json, os, pathlib, signal, socket, subprocess, time, urllib.request
root = pathlib.Path(__file__).resolve().parent.parent
runtime = root / '.local-runtime'
runtime.mkdir(exist_ok=True)
settings = root / '.env.local'
values = {}
if settings.exists():
    for line in settings.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); values[k.strip()]=v.strip()
parser=argparse.ArgumentParser()
parser.add_argument('--engine', choices=['ninfer','llama'])
parser.add_argument('--switch', action='store_true')
args=parser.parse_args()
engine=args.engine or values.get('PLANNER_ENGINE','ninfer')
alias='qwen38-ninfer-256k' if engine=='ninfer' else 'qwen3.8-27b'
port=18086 if engine=='ninfer' else 8002
url=f'http://127.0.0.1:{port}'
def read(path):
    with urllib.request.urlopen(url+path,timeout=3) as r:return json.load(r)
def matches():
    if engine=='ninfer':
        models=read('/v1/models').get('data',[])
        return any(m.get('id')==alias and m.get('owned_by')=='ninfer' and m.get('max_model_len',0)>=262144 for m in models)
    p=read('/props')
    return p.get('default_generation_settings',{}).get('n_ctx',0)>=262144 and 'Qwen3.8-27B-Q4_K_M' in p.get('model_path','')
def occupied():
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=1):return True
    except OSError:return False
def configured_path(name):
    value = values.get(name) or os.environ.get(name)
    if not value or not pathlib.Path(value).is_file():
        raise SystemExit(f'Set {name} in .env.local to a file accessible to the local runtime.')
    return value
def launch_command():
    if engine == 'ninfer':
        binary = configured_path('PLANNER_NINFER_BIN')
        model_path = configured_path('PLANNER_NINFER_MODEL_PATH')
        os.environ['CUDA_VISIBLE_DEVICES']=values.get('PLANNER_CUDA_VISIBLE_DEVICES') or os.environ.get('CUDA_VISIBLE_DEVICES','0')
        library_path = values.get('PLANNER_NINFER_LIBRARY_PATH')
        if library_path:
            os.environ['LD_LIBRARY_PATH'] = library_path
        return [binary,model_path,'--host','127.0.0.1','--port',str(port),'--device','0','--max-context','262144','--kv-capacity','262144','--max-concurrency','1','--prefill-chunk','1024','--kv-dtype','k8v4','--no-prefix-reuse','--no-thinking','--greedy','--model-id',alias,'--spec','mtp','--draft-tokens','3','--lm-head-draft']
    binary = configured_path('PLANNER_LLAMA_BIN')
    model_path = configured_path('PLANNER_LLAMA_MODEL_PATH')
    return [binary,'--model',model_path,'--alias',alias,'--host','127.0.0.1','--port',str(port),'--device','CUDA0','--fit','off','--n-gpu-layers','99','--flash-attn','on','--ctx-size','262144','--parallel','1','--cache-type-k','q4_0','--cache-type-v','q4_0','--spec-type','draft-mtp','--spec-draft-n-max','2','--threads','16','--jinja','--no-mmap']
try: compatible=matches() if occupied() else False
except Exception: compatible=False
command_to_launch = launch_command() if not compatible and (args.switch or not occupied()) else None
if args.switch and not compatible:
    pidfile=runtime/'model.pid'
    if pidfile.exists():
        pid=int(pidfile.read_text())
        cmdpath=pathlib.Path(f'/proc/{pid}/cmdline')
        command=cmdpath.read_bytes().decode().replace('\x00',' ') if cmdpath.exists() else ''
        if command:
            if not any(f'--port {p}' in command for p in (8002,18086)) or not any(s in command for s in ('llama-server','ninfer-serve')):
                raise SystemExit('Owned PID no longer matches a project model. No process stopped.')
            os.kill(pid,signal.SIGTERM)
            for _ in range(100):
                if not cmdpath.exists() or not cmdpath.read_bytes():break
                time.sleep(.2)
            else:raise SystemExit('Old model is still stopping; retry later.')
            time.sleep(2)
if occupied() and not compatible:
    raise SystemExit(f'Port {port} is occupied by another or loading profile. No new process started.')
started=False
if not occupied():
    with open(runtime/'model.log','ab') as log:
        process=subprocess.Popen(command_to_launch or launch_command(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (runtime/'model.pid').write_text(str(process.pid));started=True
    print(f'Loading {engine} / 256K...',flush=True)
for attempt in range(180):
    try: ready=matches()
    except Exception: ready=False
    if ready: break
    if started and process.poll() is not None: raise SystemExit('Model exited. See .local-runtime/model.log; use model:q4 to select the backup.')
    if attempt%15==0: print('Waiting for local model...',flush=True)
    time.sleep(2)
else: raise SystemExit('Startup timed out; loading process was left running. See .local-runtime/model.log.')
updates={'PLANNER_ENGINE':engine,'PLANNER_BASE_URL':url+'/v1','PLANNER_MODEL':alias,'PLANNER_MIN_CONTEXT':'262144','PLANNER_ENABLE_THINKING':'false'}
lines=settings.read_text(encoding='utf-8-sig').splitlines() if settings.exists() else []
lines=[line for line in lines if line.split('=',1)[0].strip() not in updates]
settings.write_text('\n'.join(lines+[f'{k}={v}' for k,v in updates.items()])+'\n',encoding='utf-8')
print(f'Ready: {alias}; context 262144; {engine}. Local project settings updated.',flush=True)
