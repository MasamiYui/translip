# Frontend 管理界面

`frontend/` 是 `translip` 的 Web 管理界面，负责创建任务、查看进度、浏览产物和维护配置预设。技术栈为 React 19、TypeScript、Vite、React Query、React Router 和 Tailwind CSS 4。

## 功能概览

- `Dashboard`
  查看任务统计和活跃流水线状态
- `Task List`
  按状态、目标语言和关键词筛选任务
- `New Task`
  通过四步表单创建新的配音任务
- `Task Detail`
  查看阶段进度、manifest、产物和重跑入口
- `Settings`
  查看设备、Python 版本、缓存和模型状态

## 本地开发

先在仓库根目录启动后端：

```bash
uv run uvicorn translip.server.app:app --host 127.0.0.1 --port 8765
```

然后在 `frontend/` 目录启动前端：

```bash
npm install
npm run dev
```

开发环境地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8765`

说明：

- `vite.config.ts` 已把 `/api` 代理到 `http://127.0.0.1:8765`
- 前端 axios 使用相对路径，不需要单独配置 API Base URL
- 如果后端端口变更，需要同步修改 `vite.config.ts`

## 构建与集成运行

构建前端：

```bash
npm install
npm run build
```

构建产物会输出到 `frontend/dist`。当该目录存在时，后端应用会自动挂载这份静态文件。

在仓库根目录启动集成版：

```bash
uv run translip-server
```

此时可直接访问 `http://127.0.0.1:8765`。

说明：

- `translip-server` 默认使用 `127.0.0.1:8765`
- 如果需要自定义地址，请改用 `uvicorn translip.server.app:app --host ... --port ...`

## 目录结构

```text
frontend/
├── src/
│   ├── api/                # API 封装
│   ├── components/         # 布局、共享组件、流水线可视化组件
│   ├── lib/                # 工具函数与常量映射
│   ├── pages/              # 页面级组件
│   ├── types/              # TypeScript 类型定义
│   ├── App.tsx             # 路由入口
│   └── main.tsx            # 应用启动入口
├── public/                 # 静态资源
├── vite.config.ts          # Vite 配置与 API 代理
└── package.json            # 前端脚本与依赖
```

## 脚本

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 启动 Vite 开发服务器 |
| `npm run build` | 进行类型检查并构建生产产物 |
| `npm run lint` | 运行 ESLint |
| `npm run preview` | 预览已构建的静态资源 |

提示：

- `npm run preview` 只负责预览前端静态文件，不会自动提供后端 API
- 如果你要联调数据，优先使用 `npm run dev` + FastAPI 后端

## 后端接口约定

前端当前依赖的主要接口：

- `/api/tasks`
  创建、查询、重跑、停止、删除任务
- `/api/tasks/{task_id}/progress`
  通过 SSE 订阅任务进度
- `/api/tasks/{task_id}/manifest`
  读取流水线 manifest
- `/api/tasks/{task_id}/artifacts`
  列出任务产物
- `/api/tasks/{task_id}/artifacts/{artifact_path}`
  下载单个产物文件
- `/api/config`
  获取默认配置与管理预设
- `/api/system`
  获取系统信息和媒体探测结果

接口定义和后端实现位于：

- [../src/translip/server/app.py](../src/translip/server/app.py)
- [../src/translip/server/routes/tasks.py](../src/translip/server/routes/tasks.py)
- [../src/translip/server/routes/progress.py](../src/translip/server/routes/progress.py)
- [../src/translip/server/routes/artifacts.py](../src/translip/server/routes/artifacts.py)
- [../src/translip/server/routes/config.py](../src/translip/server/routes/config.py)
- [../src/translip/server/routes/system.py](../src/translip/server/routes/system.py)

## 相关文档

- [../README.md](../README.md)
- [../docs/README.md](../docs/README.md)
- [../docs/frontend-management-system-design.md](../docs/frontend-management-system-design.md)
