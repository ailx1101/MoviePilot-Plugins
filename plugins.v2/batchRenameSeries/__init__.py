import os
import re
from typing import Dict, List, Optional
from app.plugins import _PluginBase
from app.core.event import EventManager, Event
from app.log import logger
from app.schemas import PluginInfo, PluginResponse

__plugin_name__ = "batch_rename_series"


class BatchRenameSeries(_PluginBase):
    """
    批量剧集重命名插件（带Web界面+预览模式）
    功能：1. Web可视化操作 2. 预览模式（不实际修改）3. 批量重命名为MP识别格式
    """
    # 插件名称
    plugin_name = "BatchRenameSeries"
    # 插件描述
    plugin_desc = "批量剧集重命名插件"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/honue/MoviePilot-Plugins/main/icons/anistrm.png"
    # 插件版本
    plugin_version = "1.1.1"
    # 插件作者
    plugin_author = "ailx1101"
    # 作者主页
    author_url = "https://github.com/ailx1101"
    # 插件配置项ID前缀
    plugin_config_prefix = "batchRenameSeries_"
    # 加载顺序
    plugin_order = 11
    # 可使用的用户级别
    auth_level = 1

    def __init__(self):
        self.plugin_info = PluginInfo(
            name="批量剧集重命名",
            author="ailx1101",
            version="1.1.1",
            description="自动按文件夹名+季集重命名剧集文件，支持Web界面和预览模式"
        )
        # 注册Web界面点击事件（与package.json中button的click对应）
        EventManager().register_event(Event("batch_rename_series:run_rename", self.run_rename))

    def start(self):
        """插件启动"""
        logger.info("批量剧集重命名插件已启动，支持Web界面和预览模式")

    def stop(self):
        """插件停止"""
        logger.info("批量剧集重命名插件已停止")

    def run_rename(self, params: Dict) -> PluginResponse:
        """
        执行批量重命名（Web界面触发，支持预览）
        :param params: Web界面传入的参数（path、season、preview）
        :return: 操作结果（含日志/预览信息）
        """
        # 解析Web界面参数
        path = str(params.get("path", "")).strip()
        is_preview = self._to_bool(params.get("preview", True))

        try:
            season = int(params.get("season", 1))
        except (TypeError, ValueError):
            log_msg = "错误：季数无效（请输入1-99之间的数字）"
            return PluginResponse(code=1, msg="季数无效", data={"log": log_msg})

        # 参数校验
        if not path:
            return PluginResponse(code=1, msg="请输入剧集根目录", data={"log": "❌ 错误：剧集根目录不能为空"})
        if not os.path.exists(path):
            log_msg = f"❌ 错误：目录不存在 → {path}"
            logger.error(log_msg)
            return PluginResponse(code=1, msg="目录不存在", data={"log": log_msg})
        if season < 1 or season > 99:
            log_msg = f"❌ 错误：季数无效（请输入1-99之间的数字）"
            return PluginResponse(code=1, msg="季数无效", data={"log": log_msg})

        # 初始化日志
        rename_log = [f"📌 操作参数：",
                      f"   - 剧集根目录：{path}",
                      f"   - 季数：S{season:02d}",
                      f"   - 模式：{'预览模式（不修改文件）' if is_preview else '实际重命名模式'}",
                      f"----------------------------------------"]

        # 遍历所有子文件夹（每个文件夹 = 1 部剧）
        for folder_path, dirs, files in os.walk(path):
            # 跳过根目录，只处理子文件夹（子文件夹名=剧集名）
            if folder_path == path:
                continue

            # 提取剧集名（文件夹名），去除特殊字符（避免命名异常）
            series_name = os.path.basename(folder_path)
            series_name = re.sub(r'[\/:*?"<>|]', "", series_name)  # 过滤非法字符
            rename_log.append(f"📺 正在处理剧集：{series_name}")

            # 获取当前文件夹下所有视频文件
            video_files = self._get_video_files(folder_path)
            if not video_files:
                rename_log.append(f"   ⚠️  无可用视频文件，跳过")
                rename_log.append("----------------------------------------")
                continue

            # 按文件名中的数字排序（确保 1、2、3... 顺序正确，避免 10 在 2 前面）
            video_files.sort(key=self._video_sort_key)

            # 处理每个视频文件
            success = 0
            fail = 0
            skip = 0

            for idx, video_file in enumerate(video_files, start=1):
                old_path = os.path.join(folder_path, video_file)
                ext = os.path.splitext(video_file)[-1].lower()  # 保留原始后缀（小写，统一规范）
                episode = self._extract_number(video_file) or idx

                # 生成新文件名（MP识别标准格式：剧名 S01E01.mp4）
                new_name = f"{series_name} S{season:02d}E{episode:02d}{ext}"
                new_path = os.path.join(folder_path, new_name)

                # 跳过已经是目标名称的文件，避免重复处理。
                if os.path.normcase(os.path.abspath(old_path)) == os.path.normcase(os.path.abspath(new_path)):
                    rename_log.append(f"   ⏩ 跳过：{video_file}（已符合MP识别格式）")
                    skip += 1
                    continue

                # 重名检查
                if os.path.exists(new_path):
                    rename_log.append(f"   ❌ 失败：{video_file} → {new_name}（文件已存在）")
                    fail += 1
                    continue

                # 预览模式：不执行重命名，仅记录结果
                if is_preview:
                    rename_log.append(f"   🔍 预览：{video_file} → {new_name}")
                    success += 1
                # 实际重命名模式：执行修改
                else:
                    try:
                        os.rename(old_path, new_path)
                        rename_log.append(f"   ✅ 成功：{video_file} → {new_name}")
                        success += 1
                    except Exception as e:
                        error_msg = str(e)[:50]  # 截取部分错误信息，避免日志过长
                        rename_log.append(f"   ❌ 失败：{video_file} → {new_name}（{error_msg}...）")
                        fail += 1

            # 单部剧处理完成日志
            rename_log.append(f"   📊 处理结果：成功{success}个 | 失败{fail}个 | 跳过{skip}个")
            rename_log.append("----------------------------------------")

        # 整体处理完成
        total_log = "\n".join(rename_log)
        logger.info(f"批量重命名操作完成（预览模式：{is_preview}）")
        return PluginResponse(
            code=0,
            msg=f"操作完成（预览模式：{is_preview}）",
            data={"log": total_log}
        )

    def _get_video_files(self, folder: str) -> List[str]:
        """获取文件夹内所有视频文件，过滤非视频格式"""
        video_exts = [".mp4", ".mkv", ".ts", ".flv", ".avi", ".mov", ".wmv", ".m4v"]
        return [
            f for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f))
            and f.lower().endswith(tuple(video_exts))
        ]

    def _extract_number(self, filename: str) -> Optional[int]:
        """提取文件名中的数字，用于排序（处理 1.mp4、01.mp4、第1集.mp4 等场景）"""
        num_match = re.findall(r'\d+', filename)
        return int(num_match[0]) if num_match else None

    def _video_sort_key(self, filename: str):
        """优先按文件名中的集数排序，无数字的文件排到最后。"""
        number = self._extract_number(filename)
        return (number is None, number or 0, filename.lower())

    def _to_bool(self, value) -> bool:
        """兼容表单中可能出现的字符串布尔值。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _is_standard_format(self, filename: str) -> bool:
        """判断文件名是否已符合 MP 剧集识别标准（SxxExx 格式）"""
        standard_pattern = r'^.+\sS\d{2}E\d{2}\.[a-zA-Z0-9]+$'
        return bool(re.match(standard_pattern, filename))


# 注册插件（MP插件必须的注册入口）
def register():
    return BatchRenameSeriesPlugin()
