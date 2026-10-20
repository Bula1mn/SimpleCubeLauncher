# SCL 发布手册

本文件对应当前 0.2.8 发布准备。

## 1. 仓库初始化

当前目录还没有 .git，也没有远端。

安装 Git 后：

    cd D:\LC
    git init
    git add .
    git status --short

确认暂存列表中没有：

- accounts.json
- config.json
- game/
- cache/
- edge-profile/
- *.zip
- SimpleCubeLauncher/
- update_url.txt

然后：

    git commit -m "SCL 0.2.8 release preparation"
    git branch -M main
    git remote add origin https://github.com/你的用户名/你的仓库.git
    git push -u origin main

## 2. 发布版本

确认以下版本号一致：

- version_info.txt
- gui.py 的 SCL v0.2.8
- launcher/__init__.py
- pyproject.toml
- main.py

打 tag：

    git tag v0.2.8
    git push origin v0.2.8

GitHub Actions 会自动：

- 构建 SimpleCubeLauncher-0.2.8-win64.zip
- 生成 SHA256SUMS.txt
- 生成 update.json
- 把 update_url.txt 放进 zip
- 创建 GitHub Release
- 上传 zip、SHA、update.json

## 3. update_url.txt

发布 zip 里会多一个：

    SimpleCubeLauncher/update_url.txt

内容形如：

    https://github.com/你的用户名/你的仓库/releases/latest/download/update.json

SCL 启动时会按以下顺序找更新地址：

1. 设置里的“更新清单 URL”
2. exe 同级的 update_url.txt
3. 没有则跳过自动检查

因此玩家不需要手动填写 URL。

## 4. update.json

GitHub Actions 会自动生成并附加到 Release：

    {
      "version": "0.2.8",
      "notes": "SCL 0.2.8。详情见 GitHub Release。",
      "url": "https://github.com/你的用户名/你的仓库/releases/download/v0.2.8/SimpleCubeLauncher-0.2.8-win64.zip",
      "sha256": "自动填写",
      "mandatory": false
    }

固定地址：

    https://github.com/你的用户名/你的仓库/releases/latest/download/update.json

## 5. 首次发布注意

- 当前 0.2.8 的本地构建包没有 update_url.txt，因为没有远端仓库信息。
- GitHub Actions 构建出来的包才有自动更新入口。
- 先用 Actions 产物发布 0.2.8；以后玩家从 0.2.9 开始能自动检查更新。
- 旧版本 0.2.7 没有内置更新地址，无法自动升级到 0.2.8，只能手动换包。

## 6. 发布前测试

- 干净 Windows 解压 zip
- 双击 exe
- 首次启动
- 微软登录
- 下载原版/整合包
- 拖入 .mrpack / .zip
- 拉伸窗口
- 从旧版本更新到新版本
- 更新后 config/accounts/instances 是否保留

## 7. 代码签名

未签名 exe 会触发 SmartScreen“未知发布者”。

购买 Windows 代码签名证书后：

    signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f cert.pfx /p 密码 SimpleCubeLauncher.exe

再压缩发布包。

## 8. 不要发布的内容

不要上传：

- D:\LC\SimpleCubeLauncher 便携运行目录
- accounts.json
- config.json
- edge-profile
- cache
- game
- 任何 Minecraft 游戏文件

只发布从 dist 构建出来的干净目录。

## 9. 推送后需要提供的信息

把 GitHub 用户名/仓库名发来后，需要：

1. 设置 origin
2. 确认 Actions 首次构建成功
3. 创建 v0.2.8 tag
4. 检查 Release 中的 zip / SHA / update.json
5. 用 0.2.8 包做一次更新链路测试
