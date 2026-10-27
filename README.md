# 🐱 找猫游戏 CatFind（OpenWrt / LuCI）

一个跑在路由器上的逻辑解谜小游戏。纯前端单文件实现，附带 OpenWrt 软件包和 LuCI 管理界面。

**玩法规则**

- 棋盘被划分为若干个**色块区域**（区域互不相连地拼接成 N×N）
- **每一行、每一列、每一个色块区域内，都恰好有一只猫**
- **猫与猫不能相邻**（含斜对角，共 8 个方向都不行）
- 点空白格排除：第一次点标记 ✕（可再点取消），点到没有猫的格子会变成**红色 ✕ 并锁定**
- 找到猫后猫头会锁定不可点击

## 直接玩

仓库根目录的 `index.html` 是完整游戏，**双击用浏览器打开即可**，不依赖任何服务端。
也可以开启 GitHub Pages，直接用网页地址访问。

## OpenWrt / iStoreOS 安装

### 方式一：装现成的 ipk

```sh
# 把 ipk/luci-app-catfind_1.2.1_all.ipk 传到路由器
opkg install luci-app-catfind_1.2.1_all.ipk
```

> **iStoreOS 注意**：它的 opkg 被 `istoreenhance` 改造过，会报
> `pkg_init_from_file: Malformed package file` 而拒绝标准 ipk。
> 改用下面的构建脚本 `--deploy`，会自动走手工登记路径（效果与安装完全一致）。

### 方式二：从源码构建 + 一键部署

```sh
cd openwrt

python3 build_ipk.py                    # 只构建，输出 ipk/luci-app-catfind_1.2.1_all.ipk
python3 build_ipk.py --deploy 192.168.2.1 --password 你的密码   # 构建并安装到路由器
```

需要 `pip install paramiko`（仅 `--deploy` 时需要）。

### 方式三：OpenWrt SDK 编译

把 `openwrt/` 整个目录放到 SDK 的 `package/` 下，注意先把根目录的 `index.html`
复制到 `openwrt/files/www/catfind/index.html`：

```sh
cp ../index.html files/www/catfind/index.html
make package/luci-app-catfind/compile V=s
```

## LuCI 管理界面

位置：**服务 → 找猫游戏**

| 项目 | 说明 |
| --- | --- |
| 启用游戏 | 开关立即生效（保存即触发，不需要"保存并应用"） |
| 网页端口 | 默认 8088，改完保存立即重启服务，不影响 LuCI 的 80 端口 |
| 访问地址 | 显示 `http://路由器IP:端口/` |
| 运行状态 | 检测端口是否真正在监听 |
| 当前进度 | 读取服务端进度文件 |
| 跳到指定关卡 | 填入任意关卡号（1–999），打开游戏直接进入该关 |

## 目录结构

```
.
├── index.html                 游戏本体（单文件，含全部 JS/CSS/音效）
├── README.md
├── openwrt/                   OpenWrt 打包源码
│   ├── Makefile               SDK 编译用
│   ├── build_ipk.py           免 SDK 直接打包 / SSH 部署
│   ├── control/               control / postinst / prerm
│   └── files/                 安装到路由器的文件（按实际路径摆放）
│       ├── etc/config/catfind             UCI 配置
│       ├── etc/init.d/catfind             procd 服务（独立 uhttpd 实例）
│       ├── usr/lib/lua/luci/...           LuCI 控制器 + CBI 界面
│       ├── www/catfind/cgi-bin/progress   进度读写接口
│       └── www/cgi-bin/catfind-setlevel   跳关接口（同源 80 端口）
└── ipk/                       已构建好的安装包
```

## 一些实现细节

**为什么最大 12×12？**
唯一解校验用的是局部搜索 + 回溯计数。实测 n=13 在 820ms 预算内唯一解收敛率 0%，
n=15 在 16.6s 内也是 0%；而 n=12 经过位掩码优化（`collectSolutions` 的 `feasible()`
预计算每个区域在每一行的列位掩码，复杂度 O(n³)→O(n²)）后稳定 100% 唯一解，
平均 465ms。所以上限定在 12。

**进度为什么不只存 localStorage？**
localStorage 是按 origin 隔离的。LuCI 改端口后 origin 变了，进度就"丢"了。
所以进度同时写到服务端 `/etc/catfind-progress.json`（通过 CGI 读写），
客户端用时间戳 `stamp` 做合并，换端口、换设备都能续上。

**音效**
内置真实猫叫（base64 内嵌 MP3），另外提供合成音、TTS 语音、"叮咚"提示音，
可在游戏菜单里切换。

**调色板**
内置马卡龙 / 莫兰迪 / 糖果 / 夜幕四套 12 色方案，色相与明度双维度错开
（相邻区域最小色距从 13.8 提升到 31.3），也支持自定义并存。

## 已知问题

- iStoreOS 的 opkg 需要手工登记路径（构建脚本已自动处理）
- uhttpd 不响应 SIGTERM，所以 init 脚本的 `stop_service` 用 `kill -9` + `sleep 1`，
  否则紧接着的 start 抢不到端口会进入崩溃重试

## License

MIT
