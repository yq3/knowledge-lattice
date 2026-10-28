"""worker 子进程入口：`python -m knowledge_lattice.worker`（design §2 部署形态——
主进程经 WorkerSupervisor 拉起本模块；装配与主循环见 runner.main）。"""

from knowledge_lattice.worker.runner import main

main()
