# Simple Cube Launcher (SCL) 完整技术档案

> 版本：0.2.8.0（发布准备版）  
> 档案时间：2026-10-21（Asia/Shanghai）  
> 项目目录：D:\LC  
> 说明：本文按当前源码、已打包程序、配置和数据目录整理；不包含账号令牌明文。

---

## 1. 产品身份

- 软件内名称：**SCL**
- 外部完整名称：**Simple Cube Launcher**
- Windows 可执行文件：SimpleCubeLauncher.exe
- 发布包：SimpleCubeLauncher-0.2.7-win64.zip
- 类型：Windows x64 原生桌面 Minecraft 启动器
- 技术路线：Python 3.12 + Tkinter，PyInstaller onedir + windowed 打包
- 许可证：MIT
- 默认窗口：1180×780，最小 900×600，无系统标题栏
- 默认游戏分辨率：960×540（配置项 width/height）
- 默认内存：4096 MB
- 当前强调色：绿色（新版 #1F9D6A / #147A50）
- 当前主页背景：晨曦（dawn）

### 当前本地发布物（GitHub Actions 产物会额外带 update_url.txt）

| 文件 | 大小 | 说明 |
|---|---:|---|
| D:\LC\SimpleCubeLauncher\SimpleCubeLauncher.exe | 5,643,340 B | 主程序 |
| D:\LC\SimpleCubeLauncher\_internal\ | 1,071 个文件 | Python/PyInstaller 运行库 |
| D:\LC\SimpleCubeLauncher-0.2.8-win64.zip | 36,137,241 B | 发布包 |
| D:\LC\SHA256SUMS.txt | 102 B | 校验文件 |

发布包 SHA256：

    	de92c86767bdb6d09ee9fefb570356d560d45f6c0773d18110217a4633b9c395

版本资源：

    FileVersion    : 0.2.7.0
    ProductVersion : 0.2.7.0
    ProductName    : Simple Cube Launcher
    InternalName   : SimpleCubeLauncher
    OriginalName   : SimpleCubeLauncher.exe

---

## 2. 版本演进

| 版本 | 主要变化 |
|---|---|
| 0.1.x | 最初的 CubeLauncher：原生 Tk 界面、实例/启动/下载/Modrinth、PyInstaller onedir。 |
| 0.2.0 | 改名 Simple Cube Launcher (SCL)；微软登录改为 PCL 授权码流程；品牌统一。 |
| 0.2.1 | 修复 Microsoft OAuth 授权 URL 被 cmd 截断导致的 AADSTS900144。 |
| 0.2.2 | 改为 Edge 远程调试捕获授权 code；Xbox RpsTicket 修正；完整正版登录成功。 |
| 0.2.3 | 完全移除系统标题栏，改为无边框 Tk 窗口；窗口控制移入界面。 |
| 0.2.4 | 下载页分页；资源包标签调整；右侧大小/简介；来源/安装/复制昵称；实例详情。 |
| 0.2.5 | 边缘缩放；页内弹层；黑色图标；极简滚动条；启动/页面动画实验。 |
| 0.2.6 | 主内容区截图淡化；Canvas 圆角按钮；设置自动保存；更新检查；整合包发布；实例目录命名；8 路下载。 |
| 0.2.7 | 移除启动/页面/标签动画与截图淡化，修黑屏；拖放不再弹确认框；支持 zip；界面冷色刷新；扁平复选框；窗口按钮缩小。 |

---

## 3. 技术栈

### 运行时

- Python 3.12（当前构建环境）
- Tkinter / ttk
- Pillow（图片缓存、预览、圆角按钮不需要 Pillow，但 Hero 背景和图片需要）
- pygame（背景音乐）
- websocket-client（Edge CDP 登录）
- ctypes / Win32 API：
  - 无边框窗口
  - WS_EX_APPWINDOW
  - 手动边缘缩放
  - WM_DROPFILES
  - DPAPI

### 构建

- PyInstaller 6.22.3
- onedir
- --windowed（无控制台）
- 图标 assets/icon.ico
- 版本资源 version_info.txt
- 资源目录 assets

### 当前依赖

    Pillow>=10
    pygame>=2.5
    websocket-client>=1.7

构建依赖：

    pyinstaller==6.22.3

---

## 4. 仓库结构

    D:\LC\
    ├─ gui.py                      4,169 行，主桌面界面
    ├─ main.py                     75 行，旧的本地 HTTP Web 入口
    ├─ launcher\
    │  ├─ __init__.py              版本号 0.2.7
    │  ├─ config.py                配置 + 实例管理，315 行
    │  ├─ tasks.py                 后台任务/进度/取消，182 行
    │  ├─ minecraft.py             原版/加载器安装，616 行
    │  ├─ modrinth.py              Modrinth + mrpack/zip，348 行
    │  ├─ launch.py                启动参数与进程，358 行
    │  ├─ java.py                  Java 探测，141 行
    │  ├─ accounts.py              账号管理，187 行
    │  ├─ microsoft.py             微软登录链，223 行
    │  ├─ edge_login.py            Edge CDP 捕获 code，171 行
    │  ├─ net.py                   HTTP/下载，232 行
    │  ├─ fsutil.py                原子写入辅助，30 行
    │  ├─ pack.py                  .mrpack 打包，91 行
    │  ├─ update.py                静态更新清单/更新应用，100 行
    │  ├─ api.py                   旧 HTTP API，15 KB
    │  ├─ dpapi.py                 Windows DPAPI
    │  └─ web\                     旧 Web UI（app.js/index.html/style.css）
    ├─ assets\                     icon、背景图
    ├─ docs\                       截图、更新示例
    ├─ game\                       游戏根目录
    ├─ SimpleCubeLauncher\         便携版应用目录
    ├─ SimpleCubeLauncher-0.2.7-win64.zip
    ├─ build.ps1
    ├─ version_info.txt
    ├─ pyproject.toml
    ├─ requirements.txt
    ├─ requirements-build.txt
    ├─ README.md
    └─ .github\workflows\build.yml

### 重要说明

main.py + launcher/api.py + launcher/web 是旧的本地 HTTP Web 架构，默认打包入口是 gui.py。当前 exe 不启动本地 Web 服务，也不打开 Edge 应用窗口。

---

## 5. 数据目录

### 源码运行

- DATA_DIR = D:\LC
- 配置：D:\LC\config.json
- 账号：D:\LC\accounts.json
- 缓存：D:\LC\cache
- 游戏根目录：D:\LC\game

### 打包运行

- CODE_DIR = exe 所在目录
- 如果 CODE_DIR 下存在 game\ 或 portable.txt，则 DATA_DIR = CODE_DIR
- 否则 DATA_DIR = %LOCALAPPDATA%\SimpleCubeLauncher
- 当前实际为便携模式：
  - D:\LC\SimpleCubeLauncher\portable.txt
  - DATA_DIR = D:\LC\SimpleCubeLauncher
  - 配置：D:\LC\SimpleCubeLauncher\config.json
  - 账号：D:\LC\SimpleCubeLauncher\accounts.json
  - 缓存：D:\LC\SimpleCubeLauncher\cache
  - Edge 登录临时配置：D:\LC\SimpleCubeLauncher\edge-profile

### 当前游戏目录

    D:\LC\game\
    ├─ assets\
    ├─ libraries\
    ├─ versions\
    ├─ instances\
    ├─ meta\
    ├─ logs\
    └─ launcher_profiles.json

当前实例目录已迁移为实例名称：

    D:\LC\game\instances\测试整合包
    D:\LC\game\instances\Forge 生存
    D:\LC\game\instances\1.20.1

实例元数据在各自的 instance.json。

---

## 6. 配置模型

Config 默认字段：

    game_root        游戏根目录
    java_path        全局 Java 路径，空=自动
    memory_mb        全局内存 MB，默认 4096
    download_source  auto / official / mirror
    download_dir     更新包/整合包/临时下载目录；空=DATA_DIR/downloads
    update_url       静态 update.json URL
    update_auto      启动自动检查更新
    player_name      离线玩家名
    width/height     游戏分辨率，不是启动器窗口
    close_on_launch  旧字段
    home_background  forest / dawn / night / minimal / custom
    background_image 自定义背景文件
    music_path       背景音乐
    music_volume     0-100
    music_autoplay   自动播放
    window_alpha     0.75-1.0
    show_home_log    首页显示运行日志
    minimize_on_launch 启动游戏后最小化
    accent           green / blue / purple

当前应用配置中：

- download_source = official
- download_dir = 空（实际回退到 D:\LC\downloads）
- update_url = 空
- update_auto = true
- home_background = dawn
- window_alpha = 1.0
- show_home_log = false

注意：download_source=official 会绕过 BMCLAPI 镜像，直接走官方源；如果下载慢，改成“自动”或“镜像”通常更好。

### instance.json 结构

    id            实例 ID（现在通常等于实例名）
    name          显示名称
    mc_version    Minecraft 版本
    version_id    实际合并版本 ID（如 1.20.1-forge-47.4.3）
    loader        {type, version} 或 null
    icon          图标 URL 或本地路径
    summary       简介
    created       创建时间戳
    last_played   最后启动时间戳
    installing    安装中标记
    java_path     可选，实例级 Java
    memory_mb     可选，实例级内存

---

## 7. 桌面 UI 架构

### 入口

gui.py 的 main() 创建 LauncherApp(tk.Tk)，进入 mainloop。  
main.py 不是当前桌面入口。

### 根窗口

- overrideredirect(True)，完全无系统标题栏
- Win32 WS_EX_APPWINDOW 保留任务栏
- DWM 圆角/边框属性
- 无 topmost
- 1180×780 启动，最小 900×600
- 右上角自绘窗口按钮

### 交互

- 拖动：侧栏品牌/标题区域手动拖动
- 双击：最大化/还原
- 缩放：鼠标靠近四边/四角自动变光标，bind_all 手动缩放
- 关闭：直接退出，无确认
- 页内弹层：账号、新建实例、项目详情、实例详情、图片预览、任务详情
- 只有微软正版授权仍使用独立 Toplevel（按历史要求保留）
- 系统文件选择器、系统消息框仍是 Windows 原生窗口

### 自绘组件

RoundedButton：

- 替代所有 tk.Button
- Canvas 画圆角矩形
- 支持文本、hover、禁用、configure/cget/invoke
- 窗口右上角使用黑图标、无背景、无边框

InlineDialog：

- Frame 覆盖层，不是新 OS 窗口
- 居中卡片
- 缩放出现动画
- 右上角关闭
- ESC 关闭

### 页面

- home
- download
- settings

用 grid_remove / grid 切换；0.2.7 已移除页面滑入/淡化/标签过渡，只保留 InlineDialog 缩放。

### 主界面分区

- 左侧栏：SCL 品牌、主页/下载/设置、账户卡、状态、退出
- 顶栏：页面标题、副标题、账户/Java/磁盘/刷新/更新按钮、窗口控制
- 主页：Hero、实例列表、日志
- 下载：游戏版本 / Mod / 光影 / 资源包 / 整合包，分页
- 设置：游戏目录、下载目录、Java、内存、下载源、玩家、个性化、音乐、发布与更新

### 图片/音乐

ImageStore：

- 网络图片缓存到 DATA_DIR/cache
- 支持本地文件
- 用于实例图标、Modrinth 预览、Hero 背景

MusicPlayer：

- pygame
- mp3 / ogg / wav
- 音量/循环/自动播放

### 线程与刷新

- TaskManager 后台线程执行安装/下载
- 主线程用 after(300) 启动 poll_loop
- poll_loop 每 800ms drain_queue、更新任务、运行状态、磁盘、日志
- background(func, done, error) 把结果投递回 Tk 主线程
- 任务异常不会直接退出；0.2.7 增加 report_callback_exception 兜底

---

## 8. 账号与微软登录

### 账号类型

1. 离线账号
   - 名称默认 Steve
   - UUID = MD5("OfflinePlayer:" + name)
2. 微软正版账号
   - 可多个
   - accounts.json 中 active 指向当前账号

当前实际：1 个微软账号，active 为 MSA；离线名 Steve。

### 存储

- accounts.json
- access_token / refresh_token 使用 Windows DPAPI 加密，前缀 dpapi:
- 非 Windows 下回退 plain:（仅开发）
- 不保存微软密码

### 登录链

1. 启动器打开 Microsoft Edge（独立临时 profile）
2. Edge 开启 remote debugging
3. 打开 login.live.com OAuth 授权页
4. Edge 在 OAuth 回调 URL 被清理前，从 CDP Network/Page 事件捕获 code
5. 用 code 换 MSA token
6. Xbox Live user/authenticate
7. XSTS authorize
8. Minecraft Services login_with_xbox
9. 获取 profile、entitlements
10. 保存 DPAPI 令牌

关键常量：

    CLIENT_ID     = 00000000402b5328（PCL 使用的公开 client id）
    SCOPE         = service::user.auth.xboxlive.com::MBI_SSL
    REDIRECT_URI  = https://login.live.com/oauth20_desktop.srf
    AUTHORITY     = https://login.live.com/oauth20_authorize.srf
    TOKEN_URL     = https://login.live.com/oauth20_token.srf

风险：client_id 不是本项目自己注册的 Azure 应用，依赖第三方公开 ID；未来可能被撤销或限制。

### Token 刷新

- AccountManager.launch_account
- 过期前 90 秒内直接使用
- 否则 refresh_account，重新保存

---

## 9. 下载架构

### 核心

launcher/net.py：

- fetch / fetch_json / fetch_json_candidates
- download_file
- 镜像映射：
  - resources.download.minecraft.net -> bmclapi2.bangbang93.com/assets/
  - libraries.minecraft.net -> bmclapi2.bangbang93.com/maven/
- source:
  - official：只用官方 URL
  - mirror / auto：镜像优先，失败回退官方
- 缓存命中：大小检查、SHA1 校验
- .part 临时文件
- 重试/回退
- 8 路 HTTP Range 大文件下载（Minecraft 客户端）
- 大于 8MB 的库文件 4 路 Range
- 资源/运行库 24 个并发 worker

### 实测

1.20.1 客户端 23,028,853 B，8 路 Range，测试环境 1.53 s。

### 版本安装

Minecraft.install：

1. 版本 JSON
2. client.jar
3. libraries
4. assets（索引 + objects）
5. logging 配置
6. 安装 marker
7. 加载器：
   - Fabric Meta API
   - Forge 官方 installer（无头运行）
   - NeoForge installer（无头运行）

### 版本清单/端点

    Mojang manifest: https://launchermeta.mojang.com/mc/game/version_manifest_v2.json
    BMCL manifest:   https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json
    Fabric Meta:     https://meta.fabricmc.net/v2
    Forge promotions:https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json
    Forge Maven:     https://maven.minecraftforge.net/net/minecraftforge/forge
    NeoForge Maven:  https://maven.neoforged.net/releases/net/neoforged/neoforge

---

## 10. 启动链路

launcher/launch.py：

1. 读取实例
2. merge_version：处理 inheritsFrom
3. required_java
4. 选择 Java：
   - 实例 java_path
   - 全局 java_path
   - 自动探测
5. 检查 Java 主版本
6. 创建 mods/shaderpacks/resourcepacks/saves/logs
7. 解压 natives 到实例 natives/
8. 构建 classpath，检查缺失库
9. 构建命令
10. 写 logs/launcher.log
11. Popen 启动 Java（CREATE_NO_WINDOW）
12. 记录 RUNNING，后台 _watch 监听退出

命令上下文包含：

- auth_player_name
- version_name
- game_directory
- assets_root
- auth_uuid
- auth_access_token
- user_type
- xuid
- classpath
- natives_directory
- library_directory
- resolution_width/height
- launcher_name/version

JVM：

- -Xms min(512, memory)
- -Xmx memory
- Java 9+ 添加 G1GC
- UTF-8
- log4j2.formatMsgNoLookups=true
- Forge 证书/补丁忽略参数
- 实例级 memory_mb 覆盖全局

当前默认 4096MB，游戏分辨率 960×540。

停止：stop_game 使用 terminate，8 秒后 kill。

日志：实例 logs/launcher.log，UI 读取尾部。

---

## 11. 内容生态

### Modrinth

API：

    https://api.modrinth.com/v2

支持：

- Mod / 光影 / 资源包 / 整合包搜索
- 游戏版本、加载器筛选
- 每页 20 条，页码翻页
- 项目图标/画廊预览/大小/可滚动简介
- 来源按钮：Modrinth
- 来源菜单：打开 Modrinth、搜索 MC百科、搜索 CurseForge
- 安装 / 复制昵称
- 安装到实例的 mods / shaderpacks / resourcepacks
- 整合包安装创建实例

### 外部来源

- MC百科：仅外部搜索链接，无直装
- CurseForge：仅外部搜索链接；API 需要 key，未直连
- CurseForge zip：读取 manifest + overrides；外部 file ID 不自动下载
- 光影需要 Iris/OptiFine 才能生效

### 整合包支持

- .mrpack（Modrinth index）
- 带 modrinth.index.json 的 zip
- 带 CurseForge manifest.json 的 zip
- 普通 zip（安装原版 + 解压目录）

当前 .mrpack 解析：
- dependencies.minecraft
- fabric-loader / forge / neoforge
- files[] 下载
- overrides / client-overrides 解压
- Quilt 显式不支持

### 整合包发布

launcher/pack.py：

- 从现有实例生成 .mrpack
- modrinth.index.json
- dependencies: minecraft + loader
- files 为空
- Mods/config/resourcepacks/shaderpacks 放 overrides
- 可选 saves/
- options.txt / servers.dat / icon
- 生成的是“overrides 携带文件”的便携包，不依赖 Modrinth 文件下载

---

## 12. 更新架构

launcher/update.py：

- 静态 update.json
- 字段：version, notes, url, sha256, mandatory
- 版本比较
- 下载更新包到 download_root/updates
- SHA256 校验
- 解压 staging
- apply_update 生成 update.bat：
  - 等待 2 秒
  - 结束 SimpleCubeLauncher.exe
  - robocopy staging/SimpleCubeLauncher -> app_dir
  - 重新启动 exe
- 保留 config/accounts/instances（zip 不包含这些）

UI：

- 设置里填 update URL
- 启动检查
- 右上角“更新 vX”
- 弹层里“立即更新/稍后”
- 开发模式不替换源码

当前 update_url 为空，所以不会自动检查/提醒。要真正分发给玩家，必须：

1. 上传新 zip 到公开静态地址
2. 上传 update.json
3. 在设置里填入 update.json URL
4. 玩家下次启动收到提醒

风险：无代码签名、无回滚、无差分更新；robocopy 期间需管理进程退出。

---

## 13. 本地 HTTP API / Web 旧界面

main.py + launcher/api.py + launcher/web：

- 本地 ThreadingHTTPServer，默认端口 17871
- 打开 Edge --app 窗口或浏览器
- 旧 UI：launcher/web/index.html / app.js / style.css
- 不是当前 exe 入口

主要 API：

    GET  /api/state
    GET  /api/versions
    GET  /api/search
    GET  /api/project
    GET  /api/logs
    GET  /api/tasks
    POST /api/config
    POST /api/instance/create
    POST /api/instance/delete
    POST /api/instance/update
    POST /api/install/vanilla
    POST /api/install/mod
    POST /api/install/shader
    POST /api/install/modpack
    POST /api/kill
    POST /api/launch
    POST /api/task/cancel
    POST /api/open-folder
    POST /api/shutdown

---

## 14. 构建与发布

### 本地

build.ps1：

- 创建 .venv
- 安装 requirements.txt + requirements-build.txt
- PyInstaller onedir windowed
- --add-data assets;assets
- --version-file version_info.txt
- 输出 dist\SimpleCubeLauncher

### CI

.github/workflows/build.yml：

- windows-latest
- Python 3.12
- 安装依赖
- PyInstaller onedir windowed
- Compress-Archive
- 上传 artifact
- tag v* 时创建 GitHub Release

### 发布包内容

- SimpleCubeLauncher.exe
- _internal/
- 不含 config.json / accounts.json / cache / edge-profile / game

当前 zip 36,137,241 B，SHA256 de92c867...。

---

## 15. 测试与调试

命令行：

    --debug
    --debug-download
    --debug-settings
    --debug-home
    --debug-settings-bottom
    --debug-account
    --debug-login
    --selftest
    --selftest-ui
    --selftest-file <path>

selftest-ui 会输出：

    SELFTEST-UI hits=... preview=... image=... hero=... cache=... music=... settings=...

当前最后一次打包版 selftest-ui：

    hits=20 preview=True image=True hero=True cache=66 music=True settings=True

其他已验证项：

- 完整 Microsoft 登录成功（历史环境）
- 8 路 23MB 客户端 1.53s
- Forge 实例打包 .mrpack 83 个文件，Forge 47.4.3 依赖
- zip drop 路由不退出
- 页面/标签/版本动画已移除
- 窗口拉伸、顶栏控制、实例迁移已测试

日志：

- DATA_DIR\gui-error.log（桌面回调异常）
- 实例 logs\launcher.log
- 根目录旧 Forge installer 日志

---

## 16. 安全与隐私

- 微软令牌 DPAPI 加密
- 不上传账号到自建服务器
- 未发现遥测/统计代码
- 图片/Modrinth 请求走外网
- PCL client_id 为公开第三方 ID，存在被撤销风险
- 更新包 SHA256 是可选校验；没有签名
- 没有代码签名证书
- 更新替换使用 robocopy，有执行权限风险
- accounts.json 含 DPAPI 密文，仍应视为敏感文件
- 不要公开 accounts.json / edge-profile

---

## 17. 当前限制与已知坑

1. update_url 为空，自动更新未启用。
2. 当前 download_source=official，下载不走 BMCLAPI；慢时可改自动/镜像。
3. MC百科/CurseForge 只有外部搜索/链接，没有直装。
4. CurseForge zip 只导入 overrides；manifest 外部文件不下载。
5. Fabric 首次启动在受限 ACL 环境可能写不了 .fabric 重映射；普通用户通常正常。
6. 不支持 Quilt。
7. 光影需要 Iris/OptiFine。
8. 实例“详情”改名不会自动重命名已存在文件夹；新实例和启动迁移才按名称。
9. 系统文件选择器、确认框、微软授权窗口仍是原生窗口。
10. 0.2.7 移除了启动/页面/标签动画；只有 InlineDialog 缩放。
11. 圆角是 Canvas 自绘按钮；卡片本身仍是矩形 Frame。
12. 更新没有回滚/签名/差分通道。
13. PCL client_id 非自有应用注册。
14. 没有自动崩溃上报。
15. 旧 HTTP Web 入口仍在源码中，但不是 exe 主入口。

---

## 18. 故障排查

### 启动器打不开

- 检查 D:\LC\SimpleCubeLauncher\gui-error.log
- 检查 accounts.json 是否损坏
- 检查 config.json 的 game_root
- 用 exe --debug 启动

### 登录失败

- Edge 是否存在
- 是否能访问 login.live.com
- 杀掉旧 msedge 调试进程
- 检查 accounts.json 是否有 dpapi 令牌
- PCL client_id 可能被限制

### 下载慢

- 设置 → 下载源：自动/镜像
- 当前 official 会绕过 BMCLAPI
- 8 路 Range 只对客户端/大库生效
- 资源并发 24，但受线路/镜像限速

### 拖入整合包退出

0.2.7 已：
- 移除确认框
- WndProc try/finally
- 回调异常兜底
- zip 分流

若仍退出，查 gui-error.log。

### 黑屏闪烁

0.2.7 已移除：
- 启动 alpha/几何动画
- 主区截图淡化
- Configure 强制重绘

如果仍出现，记录触发动作和环境（缩放/切页/多显示器/显卡）。

---

## 19. 关键结论

SCL 是一个以“单文件大 GUI + 小型启动器核心包”为特征的原生 Tk Minecraft 启动器：

- 前端：gui.py 单文件 4,169 行，强定制 Tkinter
- 核心：launcher 包 15 个模块
- 账号：离线 + 微软 PCL 授权码链 + DPAPI
- 下载：Mojang + BMCLAPI + Modrinth + Range 并发
- 启动：版本继承、Java/内存、natives、classpath
- 内容：Modrinth 完整，MC百科/CurseForge 外部链接/zip 部分
- 更新：静态 JSON + robocopy，需要自行托管
- 发布：PyInstaller onedir + GitHub Actions

