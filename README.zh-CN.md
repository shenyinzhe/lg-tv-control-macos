# LG TV Control for macOS

使用局域网控制 LG webOS 电视的原生菜单栏 App。内置运行环境，不依赖 Hammerspoon、外部 Python 或 Codex 对话目录，也不使用 HDMI-CEC。

- `Cmd + Ctrl + 1 / 2 / 3 / 4`：切换对应 HDMI。
- Mac 显示器休眠／唤醒时，先确认电视当前输入属于 Mac，再关闭／开启面板。
- 检测 LG 显示器重新接入时，尝试切到 Mac 并开屏。
- 不修改 macOS 熄屏时间、系统睡眠、电视画质或输入标签。

## 构建和配置

要求 macOS 26+、Xcode 或 Command Line Tools，以及 [uv](https://docs.astral.sh/uv/)。构建脚本使用 Python 3.13，生成的 App 自带运行环境。

```sh
./scripts/build.sh
./scripts/install.sh
helper="$HOME/Applications/LG TV Control.app/Contents/Resources/lgtv-helper/lgtv-helper"
"$helper" configure --ip 192.0.2.10 --mac-input 3
"$helper" pair
open "$HOME/Applications/LG TV Control.app"
```

把示例 IP 和 HDMI 端口替换成你的实际配置。配对时在电视上选择允许；macOS 如弹出本地网络访问请求，也需要允许。快捷键不需要辅助功能权限。

菜单标签和显示器名称可在 `~/Library/Application Support/LGTVControl/config.json` 编辑，格式参考 [config.example.json](config.example.json)，修改后重启 App。需要网络唤醒时用 `configure --mac-address … --broadcast …` 加入电视 MAC 和局域网广播地址。自动启动、唤醒或接入时先连接电视；若遇到网络错误、超时或 EWS 拒绝，则直接发送 WOL，并在重连后切到 Mac HDMI，不要求之前记录到待机。电视能正常响应且正在使用其他输入时，仍保留输入保护。

这个策略优先切回 Mac：电视服务或网络临时故障也可能导致抢走原本正在使用的输入。电源监听仅供诊断，不再作为自动唤醒的前提。

## 登录启动与卸载

```sh
./scripts/login-item.sh enable
./scripts/login-item.sh disable
```

登录启动是可选操作。卸载时先关闭登录启动，再从菜单退出 App，将 `~/Applications/LG TV Control.app` 移到废纸篓。配对凭据和配置会保留在 Application Support，只有决定清除配对时才删除该数据目录。

## 当前验证范围

前身 App 已在 M1 Pro、macOS 26.5.1、LG C3 上验证 HDMI 1–3 切换和面板控制；仓库通用版本有 20 项模拟测试和本地构建验证；已实测活动 HDMI 1 不被自动切换，以及记录完整待机后 WOL 唤醒并切 HDMI 3。真实系统睡眠／唤醒、HDMI 拔插、Intel 机器及其他型号仍需实测。睡眠过程中异步命令可能来不及完成；电视完全待机时，Mac 也可能检测不到 HDMI 接入。

源码采用 MIT 许可证。本地构建是 ad-hoc 签名，没有 Apple 公证，也没有自动更新。请勿提交 `pairing.sqlite`、实际 `config.json` 或电视状态输出。更多限制、开发说明和依赖许可见 [English README](README.md)。
