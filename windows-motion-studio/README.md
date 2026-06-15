# Windows Motion Studio

一个给 Windows 做“动效手感”配置的小工具，也可以作为 UI 动效探索、桌面体验微调和个人桌面美化的实验项目。

我做这个项目的起点很简单：手机系统已经把动画调校做得越来越细，但 Windows 桌面端大多数时候只能在“开”和“关”之间选择。Windows Motion Studio 尝试把这件事做得更细一点：按应用保存动效偏好，提供可以实际落地的系统动画调节，并保留继续扩展到特定软件、设计工具或桌面美化流程的空间。

## 中文说明

### 它能做什么

- 扫描本机已安装的 Win32 应用。
- 可选扫描 Microsoft Store / AppX 应用。
- 为不同应用保存独立动效配置。
- 提供几组预设：均衡、高效、柔和、活力、极简、自定义。
- 调整速度倍率、弹性强度和位移幅度。
- 按使用场景配置动效：页面切换、浮层弹窗、拖拽吸附、通知反馈。
- 提供一个本地预览区，用来感受不同参数下的动效节奏。
- 读写一组基础 Windows 动画注册表项。
- 支持导入、导出 JSON 配置。
- 可以打包成单文件 exe。
- 可作为 UI 动效参数尝试、桌面美化配置、应用适配器实验的基础项目。

### 系统动画调节

工具目前会读写这些当前用户注册表项：

- `HKCU\Control Panel\Desktop\WindowMetrics\MinAnimate`
- `HKCU\Control Panel\Desktop\MenuShowDelay`
- `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects\VisualFXSetting`
- `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarAnimations`

这些都是当前用户范围的设置，不需要管理员权限。部分设置可能需要注销、重新登录或重启 Explorer 后才会完全生效。

写入前工具会弹出确认，不会静默改注册表。

### 设计边界

Windows 没有提供一个统一接口，可以直接修改任意第三方应用内部动画。这个项目不会注入进程、Hook 渲染管线、反编译软件，也不会修改第三方 exe/dll。

应用级配置目前更像一个“策略库”：它会保存每个应用的动效偏好，并生成可审计的本地适配信息。以后如果某个应用提供公开配置、插件 SDK 或扩展接口，可以在这个基础上继续做专用适配。

### 可扩展方向

- 给设计师或产品经理做 UI 动效参数预览。
- 为个人桌面美化方案保存不同应用的操作节奏。
- 接入支持配置文件的工具类软件。
- 为浏览器、编辑器或创意软件编写独立适配器。
- 增加更多 Windows 外观、辅助功能和桌面体验相关设置。

### 运行源码

```powershell
pip install -e .
windows-motion-studio
```

也可以直接运行模块：

```powershell
$env:PYTHONPATH="src"
python -m windows_motion_studio
```

### 构建 exe

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

构建脚本会：

1. 安装构建依赖。
2. 生成应用图标。
3. 使用 PyInstaller 打包单文件 exe。

---

## English

Windows Motion Studio is a small desktop utility for tuning the “feel” of motion on Windows. It can also work as a playground for UI motion design, desktop experience tweaks, and personal desktop customization.

The idea is straightforward: mobile systems have become quite good at exposing animation feel and motion tuning, while Windows desktop apps usually leave users with only broad on/off choices. This project tries to make that space a bit more adjustable in a practical way, while leaving room for app-specific adapters, design tooling, and desktop customization workflows.

### What It Does

- Scans installed Win32 applications.
- Optionally scans Microsoft Store / AppX apps.
- Saves independent motion profiles per app.
- Includes presets: Balanced, Efficient, Calm, Expressive, Minimal, and Custom.
- Adjusts speed multiplier, spring strength, and motion distance.
- Configures motion by scenario: page transitions, overlays, drag snapping, and notifications.
- Provides a local preview area for motion timing.
- Reads and writes a small set of Windows animation registry preferences.
- Supports JSON import and export.
- Can be packaged as a single-file exe.
- Can be used as a starting point for UI motion experiments, desktop customization, and app adapter prototypes.

### System Animation Tweaks

The app currently reads and writes these current-user registry values:

- `HKCU\Control Panel\Desktop\WindowMetrics\MinAnimate`
- `HKCU\Control Panel\Desktop\MenuShowDelay`
- `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects\VisualFXSetting`
- `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarAnimations`

These are current-user settings and do not require administrator privileges. Some changes may require signing out, signing back in, or restarting Explorer to fully apply.

The app asks for confirmation before writing registry values.

### Scope

Windows does not expose a universal API for changing the internal animation behavior of arbitrary third-party apps. This project does not inject into processes, hook rendering pipelines, decompile software, or modify third-party exe/dll files.

Per-app configuration currently works as a policy layer: it stores motion preferences for each app and produces auditable local adapter information. If an app provides public settings, a plugin SDK, or an extension API, app-specific adapters can be added later.

### Extension Ideas

- Preview motion parameters for UI design work.
- Store app-specific motion preferences for personal desktop setups.
- Integrate with tools that expose public configuration files.
- Build dedicated adapters for browsers, editors, or creative apps.
- Add more Windows appearance, accessibility, and desktop experience settings.

### Run From Source

```powershell
pip install -e .
windows-motion-studio
```

Or run the module directly:

```powershell
$env:PYTHONPATH="src"
python -m windows_motion_studio
```

### Build The Executable

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

The build script installs build dependencies, generates the app icon, and packages a single-file exe with PyInstaller.

## Project Structure

```text
windows-motion-studio/
  assets/
  scripts/
    generate_icon.py
  src/windows_motion_studio/
    __main__.py
    app.py
    models.py
    motion_engine.py
    profile_store.py
    scanner.py
    system_tweaks.py
  build.ps1
  requirements.txt
  pyproject.toml
  README.md
  ADAPTERS.md
```
