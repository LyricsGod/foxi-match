#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接从源码目录构建 OpenWrt ipk，无需 OpenWrt SDK。

用法：
    python3 build_ipk.py                      # 生成 ipk/luci-app-catfind_<ver>_all.ipk
    python3 build_ipk.py --deploy 192.168.2.1 # 构建后通过 SSH 安装到路由器

说明：
    index.html 的源文件放在仓库根目录，构建时自动复制到包内的
    www/catfind/index.html，因此仓库里不会出现第二份副本。
"""

import argparse
import gzip
import io
import os
import shutil
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PKG = "luci-app-catfind"


def read_version() -> str:
    """版本号以 openwrt/control/control 为唯一来源，避免和代码里的常量不同步"""
    import re
    path = os.path.join(HERE, "control", "control")
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r"^Version:\s*(\S+)\s*$", f.read(), re.M)
    except OSError:
        sys.exit("读不到 control 文件: " + path)
    if not m:
        sys.exit("control 文件里没有 Version 字段: " + path)
    return m.group(1)


VERSION = read_version()

# (包内相对路径, 本地源文件, 权限)
FILES = [
    ("www/catfind/index.html",             "../index.html",                                0o644),
    ("www/catfind/cgi-bin/progress",       "files/www/catfind/cgi-bin/progress",           0o755),
    ("www/cgi-bin/catfind-setlevel",       "files/www/cgi-bin/catfind-setlevel",           0o755),
    ("etc/config/catfind",                 "files/etc/config/catfind",                     0o644),
    ("etc/init.d/catfind",                 "files/etc/init.d/catfind",                     0o755),
    ("usr/lib/lua/luci/controller/catfind.lua", "files/usr/lib/lua/luci/controller/catfind.lua", 0o644),
    ("usr/lib/lua/luci/model/cbi/catfind.lua",  "files/usr/lib/lua/luci/model/cbi/catfind.lua",  0o644),
]

CONTROL = """Package: {pkg}
Version: {ver}
Depends: luci-compat, luci-lua-runtime
Source: local
Section: luci
Priority: optional
Maintainer: local <root@localhost>
Architecture: all
Installed-Size: {size}
Description: 找猫游戏（逻辑解谜）
 带 LuCI 管理界面：开关、自定义端口、跳关；最大 12×12 且保证唯一解。
"""

POSTINST = """#!/bin/sh
[ -n "${IPKG_INSTROOT}" ] || {
\t/etc/init.d/catfind enable
\t/etc/init.d/catfind restart
\trm -rf /tmp/luci-indexcache* /tmp/luci-modulecache 2>/dev/null
}
exit 0
"""

PRERM = """#!/bin/sh
[ -n "${IPKG_INSTROOT}" ] || {
\t/etc/init.d/catfind stop
\t/etc/init.d/catfind disable
}
exit 0
"""


def gzip_bytes(raw: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as g:
        g.write(raw)
    return buf.getvalue()


def make_tar_gz(items) -> bytes:
    """items: [(name, data_bytes, mode)]"""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as t:
        for name, data, mode in items:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mtime = 1700000000
            ti.mode = mode
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "root"
            t.addfile(ti, io.BytesIO(data))
    return gzip_bytes(raw.getvalue())


def make_ar(members) -> bytes:
    """members: [(name, data_bytes)] —— 标准 ar 归档（ipk 容器）"""
    # 注意：不能用 io.BytesIO(b"!<arch>\n")，那样读写位置在 0，
    # 后续 write() 会把魔数覆盖掉，opkg 会认为这不是合法的 ipk。
    out = io.BytesIO()
    out.write(b"!<arch>\n")
    for name, data in members:
        hdr = (name.ljust(16) + "1700000000".ljust(12) + "0".ljust(6) +
               "0".ljust(6) + "100644".ljust(8) + str(len(data)).ljust(10)).encode() + b"`\n"
        assert len(hdr) == 60, len(hdr)
        out.write(hdr)
        out.write(data)
        if len(data) % 2:
            out.write(b"\n")
    return out.getvalue()


# 这些文件必须在包里，缺一个就是打包漏文件
REQUIRED = [
    "www/catfind/index.html",
    "usr/lib/lua/luci/model/cbi/catfind.lua",
    "usr/lib/lua/luci/controller/catfind.lua",
    "etc/init.d/catfind",
    "etc/config/catfind",
    "www/catfind/cgi-bin/progress",
    "www/cgi-bin/catfind-setlevel",
]

# 这几个在路由器上会被直接执行，CRLF 会让 uhttpd 报 #!/bin/sh not found
MUST_BE_LF = [
    "etc/init.d/catfind",
    "www/catfind/cgi-bin/progress",
    "www/cgi-bin/catfind-setlevel",
]


def parse_ar(blob: bytes):
    """解析 ar 归档，返回 [(name, bytes)]"""
    if not blob.startswith(b"!<arch>\n"):
        raise ValueError("不是合法的 ar 归档（缺少 !<arch> 魔数）")
    off, members = 8, []
    while off + 60 <= len(blob):
        hdr = blob[off:off + 60]
        if hdr[58:60] != b"`\n":
            raise ValueError("ar 头魔数错误，偏移 %d" % off)
        name = hdr[0:16].decode().strip().rstrip("/")
        size = int(hdr[48:58].decode().strip())
        members.append((name, blob[off + 60:off + 60 + size]))
        off += 60 + size + (size % 2)
    return members


def verify(path: str):
    """构建后自检：只用标准库，不依赖 ar / tar 命令（CI 镜像里未必有）"""
    import tarfile

    blob = open(path, "rb").read()
    ar_members = dict(parse_ar(blob))

    for need in ("debian-binary", "control.tar.gz", "data.tar.gz"):
        if need not in ar_members:
            raise SystemExit("校验失败：ar 归档里缺少 %s" % need)
    if ar_members["debian-binary"] != b"2.0\n":
        raise SystemExit("校验失败：debian-binary 内容不是 2.0")

    with tarfile.open(fileobj=io.BytesIO(ar_members["data.tar.gz"])) as t:
        names = set()
        for m in t.getmembers():
            names.add(m.name.lstrip("./"))
            if m.mode & 0o111 and not (m.mode & 0o444):
                raise SystemExit("校验失败：%s 权限异常 %o" % (m.name, m.mode))
        payload = {}
        for m in t.getmembers():
            key = m.name.lstrip("./")
            if key in MUST_BE_LF:
                payload[key] = t.extractfile(m).read()

    missing = [r for r in REQUIRED if r not in names]
    if missing:
        raise SystemExit("校验失败：包里缺少文件 -> %s" % ", ".join(missing))

    crlf = [k for k, v in payload.items() if b"\r" in v]
    if crlf:
        raise SystemExit("校验失败：以下脚本含 CR，装到路由器上会执行失败 -> %s"
                         % ", ".join(crlf))

    print("校验通过：%d 个文件，脚本均为 LF，大小 %d 字节" % (len(names), len(blob)))
    for r in REQUIRED:
        print("  ✓", r)


def read_script(name: str, fallback: str) -> str:
    """优先用 control/ 下的实际脚本文件，缺失时退回内嵌常量"""
    path = os.path.join(HERE, "control", name)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return fallback


def build() -> str:
    data_items = []
    total = 0
    for rel, src, mode in FILES:
        path = os.path.normpath(os.path.join(HERE, src))
        if not os.path.isfile(path):
            sys.exit("缺少源文件: " + path)
        with open(path, "rb") as f:
            blob = f.read()
        total += len(blob)
        data_items.append(("./" + rel, blob, mode))

    ctl_items = [
        ("./control", CONTROL.format(pkg=PKG, ver=VERSION, size=max(1, total // 1024)).encode(), 0o644),
        ("./postinst", read_script("postinst", POSTINST).encode(), 0o755),
        ("./prerm", read_script("prerm", PRERM).encode(), 0o755),
    ]

    ipk = make_ar([
        ("debian-binary", b"2.0\n"),
        ("control.tar.gz", make_tar_gz(ctl_items)),
        ("data.tar.gz", make_tar_gz(data_items)),
    ])

    outdir = os.path.join(ROOT, "ipk")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "%s_%s_all.ipk" % (PKG, VERSION))
    with open(out, "wb") as f:
        f.write(ipk)
    print("生成 %s (%.1f KB)" % (out, len(ipk) / 1024))
    verify(out)
    return out


def deploy(ipk_path: str, host: str, user: str = "root", password: str = None, port: int = 22):
    try:
        import paramiko
    except ImportError:
        sys.exit("需要 paramiko：pip install paramiko")

    if password is None:
        import getpass
        password = getpass.getpass("路由器 %s 的密码: " % host)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port, user, password, timeout=15,
                look_for_keys=False, allow_agent=False)
    sftp = ssh.open_sftp()

    remote = "/tmp/%s" % os.path.basename(ipk_path)
    sftp.put(ipk_path, remote)

    def sh(cmd):
        _, o, e = ssh.exec_command(cmd)
        return (o.read() + e.read()).decode("utf-8", "ignore").strip()

    out = sh("opkg install --force-reinstall %s 2>&1 | tail -5" % remote)
    print(out)

    installed = sh("opkg list-installed | grep %s" % PKG)
    if PKG not in installed:
        # iStoreOS 的 opkg 经过 istoreenhance 改造，会拒绝标准 ipk
        # （pkg_init_from_file: Malformed package file）。此时手工登记，
        # 效果与安装完全一致：opkg list-installed / files / remove 都正常。
        print("opkg 拒绝该包，改为手工登记 ...")
        manual_register(ssh, sftp, remote)

    # 刷新 LuCI 菜单缓存，否则新菜单不显示
    sh("rm -rf /tmp/_cf_pkg %s" % remote)
    print(sh("rm -rf /tmp/luci-indexcache* /tmp/luci-modulecache 2>/dev/null; "
             "/etc/init.d/uhttpd restart 2>&1 | tail -2; "
             "opkg list-installed | grep %s" % PKG))
    sftp.close()
    ssh.close()


def manual_register(ssh, sftp, ipk_path):
    """把包内文件解到路由器并登记进 opkg 数据库（iStoreOS 兼容路径）"""
    import time

    paths = ["/" + rel for rel, _, _ in FILES]

    def sh(cmd):
        _, o, e = ssh.exec_command(cmd)
        return (o.read() + e.read()).decode("utf-8", "ignore").strip()

    # 用路由器自带的 tar 解包，避免依赖本地实现
    print(sh("cd /tmp && rm -rf _cf_pkg && mkdir _cf_pkg && cd _cf_pkg && "
             "tar xzf %s 2>/dev/null; tar xzf data.tar.gz -C / 2>/dev/null; echo OK" % ipk_path))

    with sftp.open("/usr/lib/opkg/info/%s.control" % PKG, "w") as f:
        f.write(CONTROL.format(pkg=PKG, ver=VERSION, size=112))
    with sftp.open("/usr/lib/opkg/info/%s.list" % PKG, "w") as f:
        f.write("\n".join(paths) + "\n")

    with sftp.open("/usr/lib/opkg/status", "r") as f:
        status = f.read().decode("utf-8", "ignore")
    blocks = [b for b in status.split("\n\n") if ("Package: %s" % PKG) not in b]
    blocks.append(
        "Package: %s\nVersion: %s\nDepends: luci-compat, luci-lua-runtime\n"
        "Status: install user installed\nArchitecture: all\n"
        "Installed-Time: %d\nSection: luci\nPriority: optional\n"
        "Installed-Size: 112\nDescription: 找猫游戏（逻辑解谜）"
        % (PKG, VERSION, int(time.time()))
    )
    with sftp.open("/usr/lib/opkg/status", "w") as f:
        f.write("\n\n".join(blocks).rstrip("\n") + "\n\n")

    print(sh("/etc/init.d/catfind enable; /etc/init.d/catfind restart; echo STARTED"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", metavar="HOST", help="构建后通过 SSH 安装到该路由器")
    ap.add_argument("--user", default="root")
    ap.add_argument("--password", default=None)
    ap.add_argument("--port", type=int, default=22)
    args = ap.parse_args()

    out = build()
    if args.deploy:
        deploy(out, args.deploy, args.user, args.password, args.port)


if __name__ == "__main__":
    main()
