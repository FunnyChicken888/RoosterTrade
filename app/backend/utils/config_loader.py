import json
import os
import logging

class ConfigLoader:
    """統一的配置文件載入器"""
    
    @staticmethod
    def load_config():
        """載入配置文件，嘗試多個可能的路徑"""
        logger = logging.getLogger("ConfigLoader")
        
        # 獲取當前文件的目錄
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 定義可能的配置文件路徑（按優先級排序）
        possible_paths = [
            # 環境變量指定的路徑
            os.getenv('CONFIG_PATH'),
            # Docker 容器內路徑
            '/app/config/config.json',
            # 從 utils 目錄向上查找
            os.path.join(current_dir, '..', '..', '..', 'config', 'config.json'),
            # 從項目根目錄查找
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))), 'config', 'config.json'),
            # 相對路徑
            'config/config.json',
            # app 目錄下的配置
            os.path.join(current_dir, '..', '..', 'config', 'config.json'),
        ]
        
        # 過濾掉 None 值
        possible_paths = [path for path in possible_paths if path is not None]
        
        for config_path in possible_paths:
            try:
                # 轉換為絕對路徑
                abs_path = os.path.abspath(config_path)
                logger.debug(f"嘗試讀取配置文件: {abs_path}")
                
                if os.path.exists(abs_path):
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        logger.info(f"成功載入配置文件: {abs_path}")
                        return config, abs_path
                else:
                    logger.debug(f"配置文件不存在: {abs_path}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"配置文件格式錯誤 {abs_path}: {e}")
                continue
            except Exception as e:
                logger.debug(f"讀取配置文件失敗 {abs_path}: {e}")
                continue
        
        # 如果所有路徑都失敗，拋出異常
        logger.error("找不到有效的config.json文件")
        logger.error(f"嘗試過的路徑: {possible_paths}")
        raise FileNotFoundError("找不到有效的config.json文件")
    
    @staticmethod
    def get_config_value(key: str, default=None):
        """獲取配置值"""
        try:
            config, _ = ConfigLoader.load_config()
            return config.get(key, default)
        except Exception:
            return default
