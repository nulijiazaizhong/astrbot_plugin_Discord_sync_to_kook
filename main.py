from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, At, AtAll
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType
import asyncio
import json

@register("discord_to_kook_forwarder", "AstrBot Community", "Discord消息转发到Kook插件", "1.0.0", "https://github.com/AstrBotDevs/AstrBot")
class DiscordToKookForwarder(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 从插件元数据获取配置实例
        self.plugin_config = None
        self.config = {}
        
        # 查找当前插件的配置
        for plugin_md in context.get_all_stars():
            if plugin_md.name == "discord_to_kook_forwarder":
                if plugin_md.config and hasattr(plugin_md.config, 'keys'):
                    try:
                        self.plugin_config = plugin_md.config
                        self.config = dict(plugin_md.config)  # 转换为普通字典便于操作
                        logger.info(f"✅ 成功加载插件配置: {list(self.config.keys())}")
                    except Exception as e:
                        logger.warning(f"❌ 配置转换失败: {e}，使用默认配置")
                        self.plugin_config = None
                        self.config = {}
                break
        
        # 如果没有配置文件，使用默认值
        if not self.config:
            self.config = {
                "enabled": True,
                "discord_platform_id": "",  # Discord平台适配器ID
                "kook_platform_id": "",     # Kook平台适配器ID
                "forward_channels": {},      # Discord频道ID -> Kook频道ID的映射
                "forward_all_channels": False,  # 是否转发所有频道
                "default_kook_channel": "",  # 默认Kook频道ID
                "include_bot_messages": False,  # 是否包含机器人消息
                "message_prefix": "[Discord] ",  # 消息前缀
            }
        
        self.discord_platform = None
        self.kook_platform = None

    async def initialize(self):
        """初始化插件，获取Discord和Kook平台实例"""
        try:
            # 加载配置
            await self._load_config()
            
            # 获取平台实例
            await self._get_platform_instances()
            
            if self.discord_platform and self.kook_platform:
                logger.info("Discord到Kook转发插件初始化成功")
            else:
                logger.warning("Discord到Kook转发插件初始化失败：未找到对应的平台适配器")
        except Exception as e:
            logger.error(f"Discord到Kook转发插件初始化失败: {e}")

    async def _load_config(self):
        """加载插件配置"""
        # 配置已在__init__中加载
        pass
    
    def _save_config(self):
        """保存插件配置到文件"""
        try:
            if self.plugin_config and hasattr(self.plugin_config, 'save'):
                # 更新配置对象
                for key, value in self.config.items():
                    if hasattr(self.plugin_config, '__setitem__'):
                        self.plugin_config[key] = value
                    else:
                        setattr(self.plugin_config, key, value)
                # 保存到文件
                self.plugin_config.save()
                logger.info("✅ 插件配置已保存")
            else:
                logger.warning("❌ 无法获取插件配置实例或配置对象不支持保存，配置未保存")
        except Exception as e:
            logger.error(f"❌ 保存插件配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _get_platform_instances(self):
        """获取Discord和Kook平台实例"""
        platform_manager = self.context.platform_manager
        
        # 调试信息：显示所有可用的平台适配器
        logger.info("=== 当前系统中的所有平台适配器 ===")
        for i, platform in enumerate(platform_manager.platform_insts):
            platform_meta = platform.meta()
            logger.info(f"平台 {i+1}: 名称='{platform_meta.name}', ID='{platform_meta.id}', 描述='{platform_meta.description}'")
        logger.info("=== 平台适配器列表结束 ===")
        
        # 查找Discord平台
        for platform in platform_manager.platform_insts:
            platform_meta = platform.meta()
            if platform_meta.name == "discord":
                self.discord_platform = platform
                self.config["discord_platform_id"] = platform_meta.id
                logger.info(f"✅ 找到Discord平台: {platform_meta.id}")
                break
        else:
            logger.warning("❌ 未找到Discord平台适配器")
        
        # 查找Kook平台（通过插件提供的适配器）
        # 尝试多种可能的名称匹配
        kook_names = ["kook", "kaiheila", "开黑啦"]
        for platform in platform_manager.platform_insts:
            platform_meta = platform.meta()
            platform_name_lower = platform_meta.name.lower()
            
            # 检查是否匹配任何Kook相关的名称
            if any(name.lower() in platform_name_lower for name in kook_names):
                self.kook_platform = platform
                self.config["kook_platform_id"] = platform_meta.id
                logger.info(f"✅ 找到Kook平台: 名称='{platform_meta.name}', ID='{platform_meta.id}'")
                break
        else:
            logger.warning(f"❌ 未找到Kook平台适配器。尝试匹配的名称: {kook_names}")
            logger.warning("请确保Kook适配器插件已正确安装并启用")

    @filter.platform_adapter_type(PlatformAdapterType.DISCORD)
    async def on_discord_message(self, event: AstrMessageEvent):
        """监听Discord消息并转发到Kook"""
        try:
            logger.info(f"🔔 接收到Discord消息: 发送者={event.get_sender_name()}, 内容='{event.message_str}', 平台={event.get_platform_name()}")
            
            if not self.config["enabled"]:
                logger.info("❌ 转发功能已禁用，跳过消息")
                return
            
            if not self.kook_platform:
                logger.warning("❌ Kook平台未找到，无法转发消息")
                return
            
            # 检查是否应该转发此消息
            should_forward = await self._should_forward_message(event)
            logger.info(f"📋 消息转发检查结果: {should_forward}")
            if not should_forward:
                return
            
            # 转换消息格式
            forwarded_message = await self._convert_message_for_kook(event)
            logger.info(f"🔄 消息格式转换完成，消息链长度: {len(forwarded_message.chain)}")
            
            # 确定目标Kook频道
            target_channel = await self._get_target_kook_channel(event)
            logger.info(f"🎯 目标Kook频道: {target_channel}")
            
            if target_channel:
                # 发送到Kook
                await self._send_to_kook(target_channel, forwarded_message)
                logger.info(f"✅ 已转发Discord消息到Kook频道: {target_channel}")
            else:
                logger.warning("❌ 未找到对应的Kook频道，消息未转发")
                
        except Exception as e:
            logger.error(f"❌ 转发Discord消息到Kook时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _should_forward_message(self, event: AstrMessageEvent) -> bool:
        """判断是否应该转发此消息"""
        # 检查是否包含机器人消息
        is_bot_message = event.message_obj.sender.user_id == event.message_obj.self_id
        logger.info(f"🤖 机器人消息检查: 发送者ID={event.message_obj.sender.user_id}, 机器人ID={event.message_obj.self_id}, 是否机器人消息={is_bot_message}")
        
        if not self.config["include_bot_messages"] and is_bot_message:
            logger.info("❌ 跳过机器人消息（配置不包含机器人消息）")
            return False
        
        # 检查频道配置
        if self.config["forward_all_channels"]:
            logger.info("✅ 转发所有频道已启用，允许转发")
            return True
        
        # 检查是否在转发频道列表中
        discord_channel_id = event.message_obj.group_id or event.session_id
        logger.info(f"📍 Discord频道ID: {discord_channel_id}")
        logger.info(f"📋 配置的转发频道列表: {list(self.config['forward_channels'].keys())}")
        
        is_in_forward_list = discord_channel_id in self.config["forward_channels"]
        logger.info(f"📝 频道是否在转发列表中: {is_in_forward_list}")
        
        return is_in_forward_list

    async def _convert_message_for_kook(self, event: AstrMessageEvent) -> MessageChain:
        """将Discord消息转换为Kook格式"""
        message_chain = MessageChain()
        
        # 添加消息前缀和发送者信息
        sender_name = event.get_sender_name()
        prefix_text = f"{self.config['message_prefix']}{sender_name}: "
        message_chain.chain.append(Plain(prefix_text))
        
        # 处理消息内容
        for component in event.get_messages():
            if isinstance(component, Plain):
                message_chain.chain.append(Plain(component.text))
            elif isinstance(component, Image):
                # 保留图片
                message_chain.chain.append(component)
            elif isinstance(component, At):
                # 转换@提及为文本
                message_chain.chain.append(Plain(f"@{component.qq}"))
            elif isinstance(component, AtAll):
                # 转换@全体为文本
                message_chain.chain.append(Plain("@全体成员"))
        
        return message_chain

    async def _get_target_kook_channel(self, event: AstrMessageEvent) -> str:
        """获取目标Kook频道ID"""
        discord_channel_id = event.message_obj.group_id or event.session_id
        logger.info(f"🔍 查找目标Kook频道，Discord频道ID: {discord_channel_id}")
        
        # 检查频道映射
        if discord_channel_id in self.config["forward_channels"]:
            target = self.config["forward_channels"][discord_channel_id]
            logger.info(f"✅ 找到频道映射: {discord_channel_id} -> {target}")
            return target
        
        # 使用默认频道
        if self.config["default_kook_channel"]:
            logger.info(f"📌 使用默认Kook频道: {self.config['default_kook_channel']}")
            return self.config["default_kook_channel"]
        
        logger.warning("❌ 未找到目标Kook频道（无映射且无默认频道）")
        return None

    async def _send_to_kook(self, channel_id: str, message_chain: MessageChain):
        """发送消息到Kook频道"""
        try:
            if not self.kook_platform:
                logger.error("❌ Kook平台实例未找到，无法发送消息")
                return
            
            # 直接使用Kook适配器的客户端发送消息
            kook_client = getattr(self.kook_platform, 'client', None)
            if not kook_client:
                logger.error("❌ Kook客户端未找到，无法发送消息")
                return
                
            logger.info(f"📤 准备直接通过Kook客户端发送消息到频道: {channel_id}")
            
            # 遍历消息链中的每个组件
            for component in message_chain.chain:
                if isinstance(component, Plain):
                    await kook_client.send_text(channel_id, component.text)
                    logger.info(f"✅ 发送文本消息成功: {component.text[:50]}...")
                elif isinstance(component, Image):
                    await kook_client.send_image(channel_id, component.file)
                    logger.info(f"✅ 发送图片消息成功: {component.file}")
                else:
                    logger.warning(f"⚠️ 不支持的消息组件类型: {type(component)}")
                    
        except Exception as e:
            logger.error(f"❌ 发送消息到Kook时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())

    @filter.command("discord_kook_config")
    async def config_command(self, event: AstrMessageEvent):
        """配置Discord到Kook转发"""
        if event.role != "admin":
            yield event.plain_result("只有管理员可以配置转发设置")
            return
        
        args = event.message_str.split()[1:] if len(event.message_str.split()) > 1 else []
        
        if not args:
            # 显示当前配置
            platform_status = "✅ 已连接" if self.kook_platform else "❌ 未连接"
            config_text = f"""Discord到Kook转发配置:
启用状态: {self.config['enabled']}
Discord平台ID: {self.config['discord_platform_id']}
Kook平台ID: {self.config['kook_platform_id']}
Kook平台状态: {platform_status}
转发所有频道: {self.config['forward_all_channels']}
默认Kook频道: {self.config['default_kook_channel']}
包含机器人消息: {self.config['include_bot_messages']}
消息前缀: {self.config['message_prefix']}
频道映射: {json.dumps(self.config['forward_channels'], indent=2, ensure_ascii=False)}

使用方法:
/discord_kook_config enable/disable - 启用/禁用转发
/discord_kook_config set_kook_platform <platform_id> - 手动设置Kook平台ID
/discord_kook_config refresh_platforms - 重新检测平台适配器
/discord_kook_config set_default_channel <kook_channel_id> - 设置默认Kook频道
/discord_kook_config add_mapping <discord_channel_id> <kook_channel_id> - 添加频道映射
/discord_kook_config remove_mapping <discord_channel_id> - 移除频道映射
/discord_kook_config toggle_all_channels - 切换是否转发所有频道
/discord_kook_config quick_test <kook_channel_id> - 快速测试（启用转发所有频道到指定Kook频道）"""
            yield event.plain_result(config_text)
            return
        
        command = args[0].lower()
        
        if command == "enable":
            self.config["enabled"] = True
            self._save_config()
            yield event.plain_result("Discord到Kook转发已启用")
        elif command == "disable":
            self.config["enabled"] = False
            self._save_config()
            yield event.plain_result("Discord到Kook转发已禁用")
        elif command == "set_kook_platform" and len(args) > 1:
            platform_id = args[1]
            # 尝试根据ID找到平台
            found_platform = self.context.get_platform_inst(platform_id)
            if found_platform:
                self.kook_platform = found_platform
                self.config["kook_platform_id"] = platform_id
                self._save_config()
                yield event.plain_result(f"✅ 已手动设置Kook平台: {platform_id}")
            else:
                yield event.plain_result(f"❌ 未找到ID为 {platform_id} 的平台适配器")
        elif command == "refresh_platforms":
            await self._get_platform_instances()
            if self.kook_platform:
                yield event.plain_result("✅ 平台检测完成，已找到Kook平台")
            else:
                yield event.plain_result("❌ 平台检测完成，但仍未找到Kook平台。请检查日志获取详细信息")
        elif command == "set_default_channel" and len(args) > 1:
            self.config["default_kook_channel"] = args[1]
            self._save_config()
            yield event.plain_result(f"默认Kook频道已设置为: {args[1]}")
        elif command == "add_mapping" and len(args) > 2:
            self.config["forward_channels"][args[1]] = args[2]
            self._save_config()
            yield event.plain_result(f"已添加频道映射: {args[1]} -> {args[2]}")
        elif command == "remove_mapping" and len(args) > 1:
            if args[1] in self.config["forward_channels"]:
                del self.config["forward_channels"][args[1]]
                self._save_config()
                yield event.plain_result(f"已移除频道映射: {args[1]}")
            else:
                yield event.plain_result(f"未找到频道映射: {args[1]}")
        elif command == "toggle_all_channels":
            self.config["forward_all_channels"] = not self.config["forward_all_channels"]
            self._save_config()
            status = "启用" if self.config["forward_all_channels"] else "禁用"
            yield event.plain_result(f"转发所有频道已{status}")
        elif command == "quick_test" and len(args) > 1:
            # 快速测试配置
            kook_channel_id = args[1]
            self.config["enabled"] = True
            self.config["forward_all_channels"] = True
            self.config["default_kook_channel"] = kook_channel_id
            self.config["include_bot_messages"] = False
            self._save_config()
            yield event.plain_result(f"🚀 快速测试配置已启用！\n- 转发功能：已启用\n- 转发所有频道：已启用\n- 默认Kook频道：{kook_channel_id}\n- 包含机器人消息：已禁用\n\n现在可以在Discord发送消息进行测试！")
        else:
            yield event.plain_result("无效的配置命令，请使用 /discord_kook_config 查看帮助")

    async def terminate(self):
        """插件销毁时的清理工作"""
        logger.info("Discord到Kook转发插件已停止")
