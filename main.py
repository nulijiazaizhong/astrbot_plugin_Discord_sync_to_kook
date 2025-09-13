from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video, At, AtAll
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
        try:
            # 尝试从config.json文件加载配置
            from pathlib import Path
            
            plugin_dir = Path(__file__).parent
            config_file = plugin_dir / "config.json"
            
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                
                # 合并配置（文件配置优先）
                self.config.update(file_config)
                logger.info(f"✅ 从文件加载配置成功: {list(file_config.keys())}")
            else:
                logger.info("📄 配置文件不存在，使用默认配置")
                
            # 同步WebUI配置到内存和文件
            await self._sync_webui_config()
                
        except Exception as e:
            logger.warning(f"⚠️ 加载配置文件失败: {e}，使用默认配置")
    
    async def _sync_webui_config(self):
        """同步WebUI配置到内存和config.json文件"""
        try:
            # 如果有plugin_config对象，从中读取最新配置
            if self.plugin_config:
                webui_config = {}
                
                # 尝试读取WebUI中的配置
                config_keys = [
                    'enabled', 'discord_platform_id', 'kook_platform_id',
                    'forward_channels', 'forward_all_channels', 'default_kook_channel',
                    'include_bot_messages', 'message_prefix', 'image_cleanup_hours',
                    'video_cleanup_hours'
                ]
                
                for key in config_keys:
                    try:
                        if hasattr(self.plugin_config, '__getitem__'):
                            value = self.plugin_config.get(key)
                        elif hasattr(self.plugin_config, key):
                            value = getattr(self.plugin_config, key)
                        else:
                            continue
                            
                        if value is not None:
                            webui_config[key] = value
                    except Exception:
                        continue
                
                # 如果从WebUI读取到配置，更新内存配置
                if webui_config:
                    old_config = self.config.copy()
                    self.config.update(webui_config)
                    
                    # 检查配置是否有变化
                    if old_config != self.config:
                        logger.info(f"🔄 检测到WebUI配置变更，同步到config.json")
                        self._save_config()
                    else:
                        logger.debug("📋 WebUI配置无变化")
                        
        except Exception as e:
            logger.warning(f"⚠️ 同步WebUI配置失败: {e}")
    
    def _save_config(self):
        """保存插件配置到文件"""
        try:
            # 尝试多种方式保存配置
            saved = False
            
            # 方式1：使用plugin_config对象
            if self.plugin_config:
                try:
                    # 更新配置对象
                    for key, value in self.config.items():
                        if hasattr(self.plugin_config, '__setitem__'):
                            self.plugin_config[key] = value
                        elif hasattr(self.plugin_config, key):
                            setattr(self.plugin_config, key, value)
                    
                    # 尝试保存
                    if hasattr(self.plugin_config, 'save'):
                        self.plugin_config.save()
                        saved = True
                        logger.info("✅ 插件配置已保存（方式1）")
                except Exception as e:
                    logger.warning(f"⚠️ 方式1保存失败: {e}")
            
            # 方式2：直接写入配置文件（始终执行，确保WebUI配置同步）
            try:
                import os
                from pathlib import Path
                
                plugin_dir = Path(__file__).parent
                config_file = plugin_dir / "config.json"
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
                
                saved = True
                logger.info("✅ 插件配置已同步到config.json")
            except Exception as e:
                logger.warning(f"⚠️ 同步config.json失败: {e}")
            
            if not saved:
                logger.warning("❌ 所有配置保存方式都失败，配置未保存")
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
            
            # 每次处理消息前同步WebUI配置
            await self._sync_webui_config()
            
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
                    # 处理图片消息
                    image_url = component.file
                    filename = getattr(component, 'filename', '未知文件名')
                    
                    # 从URL中提取实际文件名
                    from urllib.parse import urlparse
                    from pathlib import Path
                    parsed_url = urlparse(image_url)
                    url_filename = Path(parsed_url.path).name
                    
                    # 优先使用URL中的文件名
                    if url_filename and '.' in url_filename:
                        display_filename = url_filename
                    elif filename and filename != '未知文件名':
                        display_filename = filename
                    else:
                        display_filename = 'image.png'
                    
                    logger.info(f"🖼️ 检测到图片组件: URL={image_url}, 文件名={display_filename}")
                    
                    if image_url:
                        try:
                            # 下载Discord图片到本地
                            local_image_path = await self._download_image(image_url, filename)
                            if local_image_path:
                                # 使用本地图片路径发送到Kook
                                logger.info(f"📤 准备发送本地图片到Kook: {local_image_path}")
                                success = await kook_client.send_image(channel_id, local_image_path)
                                if success:
                                    logger.info(f"✅ 发送图片消息成功: {display_filename}")
                                else:
                                    logger.error(f"❌ 发送图片到Kook失败: {display_filename}")
                                    await kook_client.send_text(channel_id, f"[图片发送失败: {display_filename}]")
                            else:
                                logger.error("❌ 图片下载失败")
                                await kook_client.send_text(channel_id, f"[图片下载失败: {display_filename}]")
                        except Exception as img_error:
                            logger.error(f"❌ 发送图片失败: {img_error}")
                            import traceback
                            logger.error(traceback.format_exc())
                            # 如果图片发送失败，发送一个文本提示
                            await kook_client.send_text(channel_id, f"[图片转发失败: {display_filename}]")
                    else:
                        logger.warning("⚠️ 图片组件没有有效的文件URL")
                        await kook_client.send_text(channel_id, "[图片信息缺失]")
                elif isinstance(component, Video):
                    # 处理视频消息
                    video_url = component.file
                    filename = getattr(component, 'filename', '未知文件名')
                    
                    # 从URL中提取实际文件名
                    from urllib.parse import urlparse
                    from pathlib import Path
                    parsed_url = urlparse(video_url)
                    url_filename = Path(parsed_url.path).name
                    
                    # 优先使用URL中的文件名
                    if url_filename and '.' in url_filename:
                        display_filename = url_filename
                    elif filename and filename != '未知文件名':
                        display_filename = filename
                    else:
                        display_filename = 'video.mp4'
                    
                    logger.info(f"🎬 检测到视频组件: URL={video_url}, 文件名={display_filename}")
                    
                    if video_url:
                        try:
                            # 下载Discord视频到本地
                            local_video_path = await self._download_video(video_url, filename)
                            if local_video_path:
                                # 使用本地视频路径发送到Kook
                                logger.info(f"📤 准备发送本地视频到Kook: {local_video_path}")
                                success = await kook_client.send_video(channel_id, local_video_path)
                                if success:
                                    logger.info(f"✅ 发送视频消息成功: {display_filename}")
                                else:
                                    logger.error(f"❌ 发送视频到Kook失败: {display_filename}")
                                    await kook_client.send_text(channel_id, f"[视频发送失败: {display_filename}]")
                            else:
                                logger.error("❌ 视频下载失败")
                                await kook_client.send_text(channel_id, f"[视频下载失败: {display_filename}]")
                        except Exception as video_error:
                            logger.error(f"❌ 发送视频失败: {video_error}")
                            import traceback
                            logger.error(traceback.format_exc())
                            # 如果视频发送失败，发送一个文本提示
                            await kook_client.send_text(channel_id, f"[视频转发失败: {display_filename}]")
                    else:
                        logger.warning("⚠️ 视频组件没有有效的文件URL")
                        await kook_client.send_text(channel_id, "[视频信息缺失]")
                else:
                    logger.warning(f"⚠️ 不支持的消息组件类型: {type(component)}")
                    
        except Exception as e:
            logger.error(f"❌ 发送消息到Kook时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _download_video(self, video_url: str, filename: str) -> str:
        """下载Discord视频到本地public/video文件夹"""
        import aiohttp
        import os
        import uuid
        from pathlib import Path
        from urllib.parse import urlparse
        
        try:
            # 创建public/video目录
            plugin_dir = Path(__file__).parent
            video_dir = plugin_dir / "public" / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            
            # 从URL中提取文件名
            parsed_url = urlparse(video_url)
            url_filename = Path(parsed_url.path).name  # 获取路径中的文件名
            
            # 如果URL中有文件名，使用它；否则使用传入的filename
            if url_filename and '.' in url_filename:
                actual_filename = url_filename
            elif filename and filename != '未知文件名':
                actual_filename = filename
            else:
                actual_filename = 'video.mp4'
            
            logger.info(f"📝 提取的视频文件名: {actual_filename}")
            
            # 生成唯一的文件名，保留原始扩展名
            file_ext = Path(actual_filename).suffix if actual_filename else '.mp4'
            unique_filename = f"{uuid.uuid4().hex}{file_ext}"
            local_path = video_dir / unique_filename
            
            logger.info(f"📥 开始下载视频: {video_url} -> {local_path}")
            
            # 下载视频
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url) as response:
                    if response.status == 200:
                        with open(local_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        logger.info(f"✅ 视频下载成功: {local_path}")
                        
                        # 下载完成后进行清理
                        await self._cleanup_old_videos()
                        
                        return str(local_path)
                    else:
                        logger.error(f"❌ 下载视频HTTP错误: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ 下载视频异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def _cleanup_old_videos(self):
        """根据配置清理旧视频文件"""
        import os
        import time
        from pathlib import Path
        
        try:
            # 获取清理时间配置（小时）
            cleanup_hours = self.config.get('video_cleanup_hours', 24)
            
            # 如果设置为0，则不清理
            if cleanup_hours <= 0:
                return
                
            plugin_dir = Path(__file__).parent
            video_dir = plugin_dir / "public" / "video"
            
            if not video_dir.exists():
                return
                
            current_time = time.time()
            cleanup_count = 0
            cleanup_seconds = cleanup_hours * 3600  # 转换为秒
            
            # 清理超过配置时间的视频文件
            for video_file in video_dir.glob("*"):
                if video_file.is_file() and video_file.name != ".gitkeep":
                    file_age = current_time - video_file.stat().st_mtime
                    if file_age > cleanup_seconds:
                        try:
                            video_file.unlink()
                            cleanup_count += 1
                        except Exception as e:
                            logger.warning(f"⚠️ 删除旧视频文件失败: {video_file} - {e}")
            
            if cleanup_count > 0:
                logger.info(f"🧹 清理了 {cleanup_count} 个超过 {cleanup_hours} 小时的旧视频文件")
                
        except Exception as e:
            logger.error(f"❌ 清理旧视频文件异常: {e}")

    async def _download_image(self, image_url: str, filename: str) -> str:
        """下载Discord图片到本地public/image文件夹"""
        import aiohttp
        import os
        import uuid
        from pathlib import Path
        from urllib.parse import urlparse
        
        try:
            # 创建public/image目录
            plugin_dir = Path(__file__).parent
            image_dir = plugin_dir / "public" / "image"
            image_dir.mkdir(parents=True, exist_ok=True)
            
            # 从URL中提取文件名
            parsed_url = urlparse(image_url)
            url_filename = Path(parsed_url.path).name  # 获取路径中的文件名
            
            # 如果URL中有文件名，使用它；否则使用传入的filename
            if url_filename and '.' in url_filename:
                actual_filename = url_filename
            elif filename and filename != '未知文件名':
                actual_filename = filename
            else:
                actual_filename = 'image.png'
            
            logger.info(f"📝 提取的文件名: {actual_filename}")
            
            # 生成唯一的文件名，保留原始扩展名
            file_ext = Path(actual_filename).suffix if actual_filename else '.png'
            unique_filename = f"{uuid.uuid4().hex}{file_ext}"
            local_path = image_dir / unique_filename
            
            logger.info(f"📥 开始下载图片: {image_url} -> {local_path}")
            
            # 下载图片
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        with open(local_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        logger.info(f"✅ 图片下载成功: {local_path}")
                        
                        # 下载完成后进行清理
                        await self._cleanup_old_images()
                        
                        return str(local_path)
                    else:
                        logger.error(f"❌ 下载图片HTTP错误: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ 下载图片异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def _cleanup_old_images(self):
        """根据配置清理旧图片文件"""
        import os
        import time
        from pathlib import Path
        
        try:
            # 获取清理时间配置（小时）
            cleanup_hours = self.config.get('image_cleanup_hours', 24)
            
            # 如果设置为0，则不清理
            if cleanup_hours <= 0:
                return
                
            plugin_dir = Path(__file__).parent
            image_dir = plugin_dir / "public" / "image"
            
            if not image_dir.exists():
                return
                
            current_time = time.time()
            cleanup_count = 0
            cleanup_seconds = cleanup_hours * 3600  # 转换为秒
            
            # 清理超过配置时间的图片文件
            for image_file in image_dir.glob("*"):
                if image_file.is_file() and image_file.name != ".gitkeep":
                    file_age = current_time - image_file.stat().st_mtime
                    if file_age > cleanup_seconds:
                        try:
                            image_file.unlink()
                            cleanup_count += 1
                        except Exception as e:
                            logger.warning(f"⚠️ 删除旧图片文件失败: {image_file} - {e}")
            
            if cleanup_count > 0:
                logger.info(f"🧹 清理了 {cleanup_count} 个超过 {cleanup_hours} 小时的旧图片文件")
                
        except Exception as e:
            logger.error(f"❌ 清理旧图片文件异常: {e}")

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
                /discord_kook_config quick_test <kook_channel_id> - 快速测试（启用转发所有频道到指定Kook频道）
                /discord_kook_config cleanup_images - 立即清理旧图片文件
                /discord_kook_config cleanup_videos - 立即清理旧视频文件
                /discord_kook_config set_cleanup_hours <hours> - 设置图片清理时间（小时，0表示不自动清理）
                /discord_kook_config set_video_cleanup_hours <hours> - 设置视频清理时间（小时，0表示不自动清理）"""
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
        elif command == "cleanup_images":
            # 立即清理旧图片文件
            await self._cleanup_old_images()
            yield event.plain_result("🧹 图片清理完成")
        elif command == "cleanup_videos":
            # 立即清理旧视频文件
            await self._cleanup_old_videos()
            yield event.plain_result("🧹 视频清理完成")
        elif command == "set_cleanup_hours" and len(args) > 1:
            try:
                hours = int(args[1])
                if hours < 0:
                    yield event.plain_result("❌ 清理时间不能为负数")
                else:
                    self.config["image_cleanup_hours"] = hours
                    self._save_config()
                    if hours == 0:
                        yield event.plain_result("✅ 已禁用自动图片清理")
                    else:
                        yield event.plain_result(f"✅ 图片清理时间已设置为 {hours} 小时")
            except ValueError:
                yield event.plain_result("❌ 请输入有效的小时数")
        elif command == "set_video_cleanup_hours" and len(args) > 1:
            try:
                hours = int(args[1])
                if hours < 0:
                    yield event.plain_result("❌ 清理时间不能为负数")
                else:
                    self.config["video_cleanup_hours"] = hours
                    self._save_config()
                    if hours == 0:
                        yield event.plain_result("✅ 已禁用自动视频清理")
                    else:
                        yield event.plain_result(f"✅ 视频清理时间已设置为 {hours} 小时")
            except ValueError:
                yield event.plain_result("❌ 请输入有效的小时数")
        else:
            yield event.plain_result("无效的配置命令，请使用 /discord_kook_config 查看帮助")

    async def terminate(self):
        """插件销毁时的清理工作"""
        logger.info("Discord到Kook转发插件已停止")
