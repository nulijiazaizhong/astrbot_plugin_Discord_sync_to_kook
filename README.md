# Discord到Kook消息转发插件

这是一个为AstrBot开发的插件，用于将Discord平台的消息自动转发到Kook平台。

## 功能特性

- 🔄 **自动消息转发**: 监听Discord消息并自动转发到指定的Kook频道
- 🎯 **频道映射**: 支持Discord频道到Kook频道的一对一映射
- 🌐 **全频道转发**: 可选择转发所有Discord频道的消息
- 🤖 **机器人消息过滤**: 可配置是否包含机器人发送的消息
- 🏷️ **消息前缀**: 为转发的消息添加自定义前缀标识
- ⚙️ **动态配置**: 通过指令实时配置转发规则

## 前置要求

1. **AstrBot v4.0.0+**: 确保你的AstrBot版本支持插件系统
2. **Discord适配器**: 需要配置并启用Discord官方适配器
3. **Kook适配器**: 需要安装并配置[Kook适配器插件](https://github.com/wuyan1003/astrbot_plugin_kook_adapter)

## 安装方法

1. 将插件文件放置在AstrBot的 `data/plugins/` 目录下
2. 重启AstrBot或在插件管理页面重载插件
3. 确保Discord和Kook适配器都已正确配置并运行

## 配置说明

### 基本配置

插件会自动检测已配置的Discord和Kook平台适配器。如果检测失败，请检查：

- Discord适配器是否正确配置并启用
- Kook适配器插件是否正确安装并配置
- 两个适配器是否都处于在线状态

### 使用配置指令

使用 `/discord_kook_config` 指令来配置转发规则：

```
# 查看当前配置
/discord_kook_config

# 启用/禁用转发
/discord_kook_config enable
/discord_kook_config disable

# 设置默认Kook频道（当没有特定映射时使用）
/discord_kook_config set_default_channel <kook_channel_id>

# 添加频道映射（Discord频道ID -> Kook频道ID）
/discord_kook_config add_mapping <discord_channel_id> <kook_channel_id>

# 移除频道映射
/discord_kook_config remove_mapping <discord_channel_id>

# 切换是否转发所有频道
/discord_kook_config toggle_all_channels
```

### 获取频道ID

**Discord频道ID获取方法：**
1. 在Discord中开启开发者模式（用户设置 -> 高级 -> 开发者模式）
2. 右键点击频道名称，选择"复制ID"

**Kook频道ID获取方法：**
1. 在Kook中右键点击频道
2. 选择"复制频道链接"
3. 链接中的数字部分即为频道ID

## 配置示例

```bash
# 设置默认转发频道
/discord_kook_config set_default_channel 1234567890

# 添加特定频道映射
/discord_kook_config add_mapping 987654321 1234567890
/discord_kook_config add_mapping 111222333 4445556666

# 启用转发
/discord_kook_config enable
```

## 消息格式

转发的消息格式为：
```
[Discord] 用户名: 消息内容
```

- 文本消息会完整保留
- 图片会尝试转发（取决于Kook适配器的支持情况）
- @提及会转换为文本格式
- @全体成员会转换为"@全体成员"文本

## 注意事项

1. **权限要求**: 配置指令需要管理员权限
2. **频道ID**: 请确保提供的频道ID正确且机器人有相应权限
3. **消息限制**: 转发受到目标平台的消息长度和格式限制
4. **性能考虑**: 大量消息转发可能影响性能，建议合理配置转发规则

## 故障排除

### 常见问题

**Q: 插件初始化失败，提示未找到平台适配器**
A: 检查Discord和Kook适配器是否正确安装并启用，确保它们处于在线状态。

**Q: 消息无法转发到Kook**
A: 
- 检查Kook频道ID是否正确
- 确认机器人在目标Kook频道有发送消息的权限
- 查看AstrBot日志获取详细错误信息

**Q: 只想转发特定频道的消息**
A: 不要启用"转发所有频道"，只添加需要的频道映射即可。

### 日志查看

插件会在AstrBot日志中记录详细的运行信息，包括：
- 平台适配器检测结果
- 消息转发成功/失败信息
- 配置变更记录

## 开发信息

- **版本**: v1.0.0
- **作者**: AstrBot Community
- **许可证**: 与AstrBot主项目相同
- **仓库**: https://github.com/AstrBotDevs/AstrBot

## 贡献

欢迎提交Issue和Pull Request来改进这个插件！

## 更新日志

### v1.0.0
- 初始版本发布
- 支持Discord到Kook的基本消息转发
- 支持频道映射和配置管理
- 支持消息格式转换
