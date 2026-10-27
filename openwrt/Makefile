include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-catfind
PKG_VERSION:=1.2.1
PKG_RELEASE:=1
PKG_ARCH:=all
PKG_LICENSE:=MIT
PKG_MAINTAINER:=local <root@localhost>

LUCI_TITLE:=CatFind Puzzle (找猫游戏)
LUCI_DEPENDS:=+luci-compat +luci-lua-runtime
LUCI_PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/$(PKG_NAME)
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=$(LUCI_TITLE)
  DEPENDS:=$(LUCI_DEPENDS)
  PKGARCH:=all
endef

define Package/$(PKG_NAME)/description
	逻辑解谜小游戏：每行、每列、每个色块各有一只猫，且猫不能相邻。
	最大 12x12 且保证唯一解。带 LuCI 管理界面：服务开关、自定义端口、
	查看进度、跳转到任意关卡。
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/$(PKG_NAME)/install
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_CONF) ./files/etc/config/catfind $(1)/etc/config/catfind
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/etc/init.d/catfind $(1)/etc/init.d/catfind
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/controller
	$(INSTALL_DATA) ./files/usr/lib/lua/luci/controller/catfind.lua $(1)/usr/lib/lua/luci/controller/catfind.lua
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/model/cbi
	$(INSTALL_DATA) ./files/usr/lib/lua/luci/model/cbi/catfind.lua $(1)/usr/lib/lua/luci/model/cbi/catfind.lua
	$(INSTALL_DIR) $(1)/www/catfind/cgi-bin
	$(INSTALL_BIN) ./files/www/catfind/cgi-bin/progress $(1)/www/catfind/cgi-bin/progress
	$(INSTALL_DIR) $(1)/www/cgi-bin
	$(INSTALL_BIN) ./files/www/cgi-bin/catfind-setlevel $(1)/www/cgi-bin/catfind-setlevel
	$(INSTALL_DIR) $(1)/www/catfind
	$(INSTALL_DATA) ./files/www/catfind/index.html $(1)/www/catfind/index.html
endef

define Package/$(PKG_NAME)/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || {
	/etc/init.d/catfind enable
	/etc/init.d/catfind restart
	rm -rf /tmp/luci-indexcache* /tmp/luci-modulecache 2>/dev/null
}
exit 0
endef

define Package/$(PKG_NAME)/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || {
	/etc/init.d/catfind stop
	/etc/init.d/catfind disable
}
exit 0
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
