## about the Python REPL

This Python REPL component uses CPython compiled to WASM.

If you want build it in yourself machine.
you can use the `Dockerfile` which next to this markdown file.

run this command to build the python wasm (change the command if you use docker)

```shell
podman build --target exporter -o type=local,dest=./dist .
```

you will get some files if you build it successfully.
you can upload them to OSS or use Django import it directly
(put item to any static dir & adjust `PYTHON_WORKER_URL` var at `python.worker.ts`).
but add to git is not recommended.

### about the patchs

- python_worker: the CPython origin impl is relative request. this patch make it absolute
- test_module: as its name, just a test module, test Python3.15 lazy import
