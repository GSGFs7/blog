import { createSignal, onCleanup, onMount } from "solid-js";

const tasks = [
  "🛠️ 构建环境",
  "📦 安装依赖",
  "🧩 加载组件",
  "📝 写入配置",
  "🔒 校验权限",
  "📊 统计信息",
  "🖼️ 加载资源",
  "⏳ 等待响应",
  "🧰 准备工具",
  "🎉 即将完成",
  "🔧 配置参数",
  "🎨 渲染界面",
  "🧪 运行测试",
  "🧹 清理缓存",
  "📦 打包资源",
  "🚀 准备发布",
  "🌠 正在许愿",
  "🌐 连接服务器",
  "🧭 导航初始化",
  "🤔 重新计算中",
  "🪄 魔法加载中",
  "🔍 扫描文件系统",
  "📁 创建目录结构",
  "😅 出了点小问题",
  "💫 魔法正在发生",
  "🎲 触发随机事件",
  "🔄 正在同步数据",
];

const defaultTitle = "施工中";
const defaultMessage = "正在努力创建新文件夹";

interface Props {
  title?: unknown;
  message?: unknown;
}

export function WIP(props: Readonly<Props>) {
  const [progress, setProgress] = createSignal(0);
  const [taskIndex, setTaskIndex] = createSignal(0);
  const [isDizzy, setIsDizzy] = createSignal(false);
  const title = typeof props.title === "string" ? props.title : defaultTitle;
  const message = typeof props.message === "string" ? props.message : defaultMessage;
  let timer: number | undefined = undefined;

  onMount(() => {
    timer = setInterval(
      () => {
        setProgress((previous) => {
          let next = previous;
          while (next === previous) {
            next = Math.floor(Math.random() * 256);
          }
          return next;
        });

        setTaskIndex(
          (previous) =>
            (previous + 1 + Math.floor(Math.random() * (tasks.length - 1))) % tasks.length,
        );

        if (Math.random() < 0.03) {
          setIsDizzy(true);
        }
      },
      350 + Math.random() * 100,
    );
  });

  onCleanup(() => {
    if (timer !== undefined) {
      clearInterval(timer);
    }
  });

  return (
    <div class="mb-8" aria-hidden="true">
      <span class="mb-8 block animate-spin text-center text-6xl">{isDizzy() ? "🌀" : "⚠️"}</span>
      <h1 class="mb-4 text-center text-4xl font-bold text-white md:text-5xl">{title}</h1>
      <p class="mb-8 max-w-md text-center text-lg text-gray-300">{message}</p>
      <div class="w-64 rounded-full bg-gray-700">
        <div
          class="h-2 animate-pulse rounded-full bg-linear-to-r from-blue-500 to-purple-600"
          style={{ width: `${progress()}px` }}
        />
      </div>
      <p class="text-center">当前进度: {tasks[taskIndex()]}</p>
    </div>
  );
}
