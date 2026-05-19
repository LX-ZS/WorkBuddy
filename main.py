#!/usr/bin/env python3
"""
main.py — CLI 入口（保持原有命令行运行方式）
=============================================
所有核心逻辑已移至 backend.py，此文件仅作为 CLI 入口。
"""
import argparse
from backend import WorkStatusMonitor, CONFIG, load_config, save_config


def main():
    parser = argparse.ArgumentParser(description="智能工作状态监测系统（CLI模式）")
    parser.add_argument("--api-url",  default=None, help="豆包API base_url")
    parser.add_argument("--api-key",  default=None, help="豆包API key")
    parser.add_argument("--model",    default=None, help="豆包模型ID")
    parser.add_argument("--hour",     type=int, default=None, help="日报生成小时（24h）")
    parser.add_argument("--minute",   type=int, default=None, help="日报生成分钟")
    parser.add_argument("--save",     action="store_true", help="保存当前配置到 config.json")
    args = parser.parse_args()

    load_config()

    if args.api_url:  CONFIG["doubao_base_url"] = args.api_url
    if args.api_key:  CONFIG["doubao_api_key"]  = args.api_key
    if args.model:    CONFIG["doubao_model"]     = args.model
    if args.hour is not None:  CONFIG["report_hour"]   = args.hour
    if args.minute is not None: CONFIG["report_minute"] = args.minute

    if args.save:
        save_config()
        print("配置已保存到 config.json")

    monitor = WorkStatusMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
