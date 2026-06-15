# Adapter Notes

Windows Motion Studio keeps a clear line between “settings I can safely write” and “things that belong to a specific app”.

The app does not patch binaries, inject into processes, or hook rendering pipelines. For application-level animation control, the preferred path is always a documented configuration file, plugin API, extension API, or vendor SDK.

## 中文说明

### 当前适配层级

**Level 0: 保存配置**

默认能力。工具识别应用后，可以为它保存独立的动效偏好。

**Level 1: 系统偏好**

工具可以调整少量当前用户范围的 Windows 动画偏好，例如窗口动画、任务栏动画、菜单延迟和视觉效果策略。

**Level 2: 公开配置**

如果目标应用提供配置文件、命令行参数、插件系统或 SDK，可以基于当前配置结构继续编写适配器。

可能的例子：

- 编辑器或开发工具：写入用户设置文件。
- 浏览器：通过扩展、策略或实验性配置控制局部效果。
- 创意软件：通过官方脚本或插件 SDK 接入工作区偏好。

**Level 3: 专用插件**

对 VS Code、浏览器、Adobe 系软件等复杂应用，更适合使用官方插件体系做专用适配，而不是直接改应用本体。

### 不做的事

- 不修改第三方 exe 或 dll。
- 不注入进程。
- 不 Hook 渲染管线。
- 不绕过应用沙箱。
- 不静默写入系统级注册表。

这些限制是为了让项目更稳定，也更适合公开维护。

## English

### Adapter Levels

**Level 0: Profile storage**

The default behavior. Once an app is detected, Windows Motion Studio can store a dedicated motion profile for it.

**Level 1: System preferences**

The tool can adjust a small set of current-user Windows animation preferences, such as window animation, taskbar animation, menu delay, and visual effects policy.

**Level 2: Public configuration**

If a target app exposes config files, command-line options, plugin APIs, extension APIs, or SDKs, adapters can be built on top of the existing profile structure.

Possible examples:

- Editors or development tools: write user settings.
- Browsers: use extensions, policies, or experimental settings for local effects.
- Creative tools: integrate through official scripting or plugin SDKs.

**Level 3: Dedicated plugins**

For complex apps such as VS Code, browsers, and Adobe tools, dedicated plugins are a better direction than modifying the host application directly.

### Non-goals

- No third-party exe/dll modification.
- No process injection.
- No rendering pipeline hooks.
- No sandbox bypassing.
- No silent system-level registry writes.

These boundaries keep the project safer, easier to maintain, and more realistic as a public personal project.
