"""Mukou Aoi 安装脚本 — 将插件/技能部署到 Hermes Agent"""

import json
import os
import shutil
import sys
from pathlib import Path


def get_hermes_home() -> Path:
    """获取 Hermes 主目录"""
    env = os.getenv("HERMES_HOME") or os.getenv("HOME")
    if env:
        return Path(env) / ".hermes"
    return Path.home() / ".hermes"


def install_plugins(hermes_home: Path, source_dir: Path):
    """安装 emotion-governor 和 mode-switch 插件"""
    plugins_src = source_dir / "plugins"
    plugins_dst = hermes_home / "hermes-agent" / "plugins"

    print(f"📦 安装插件到: {plugins_dst}")
    plugins_dst.mkdir(parents=True, exist_ok=True)

    for plugin_name in ["emotion-governor", "mode-switch"]:
        src = plugins_src / plugin_name
        dst = plugins_dst / plugin_name

        if dst.exists():
            print(f"  ⚠️  {plugin_name} 已存在，覆盖中...")
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"  ✅ {plugin_name}")

    print()


def install_skills(hermes_home: Path, source_dir: Path):
    """安装可复用的 Skill 文档到用户 skills 目录"""
    skills_src = source_dir / "skills"
    skills_dst = hermes_home / "skills"

    print(f"📄 安装 skills 到: {skills_dst}")
    skills_dst.mkdir(parents=True, exist_ok=True)

    for skill_dir in skills_src.iterdir():
        if not skill_dir.is_dir():
            continue
        dst = skills_dst / skill_dir.name
        if dst.exists():
            print(f"  ⚠️  {skill_dir.name} 已存在，跳过（手动删除后再安装）")
            continue
        shutil.copytree(skill_dir, dst)
        print(f"  ✅ {skill_dir.name}")

    print()


def install_config_examples(hermes_home: Path, source_dir: Path):
    """安装示例配置（不会覆盖已有文件）"""
    examples_src = source_dir / "examples"
    dst = hermes_home

    print(f"📋 安装示例配置到: {dst}")
    for f in examples_src.iterdir():
        if not f.is_file():
            continue
        dst_path = dst / f.name
        if dst_path.exists():
            print(f"  ⚠️  {f.name} 已存在，跳过")
            continue
        shutil.copy2(f, dst_path)
        print(f"  ✅ {f.name}")

    print()


def install_tone_map(hermes_home: Path, source_dir: Path):
    """安装 tone_map.json（不覆盖已有）"""
    src = source_dir / "mukou_aoi" / "examples" / "tone_map.json"
    dst = hermes_home / "tone_map.json"
    if dst.exists():
        print(f"  ⚠️  tone_map.json 已存在，跳过")
        return
    shutil.copy2(src, dst)
    print(f"  ✅ tone_map.json")


def main():
    source_dir = Path(__file__).parent.parent.resolve()
    hermes_home = get_hermes_home()

    print(f"🔧 Mukou Aoi 安装工具")
    print(f"   Hermes 目录: {hermes_home}")
    print(f"   安装源:      {source_dir}")
    print()

    if not hermes_home.exists():
        print(f"❌ Hermes 目录不存在: {hermes_home}")
        print("   请先安装 Hermes Agent 或设置 HERMES_HOME 环境变量")
        sys.exit(1)

    install_plugins(hermes_home, source_dir)
    install_skills(hermes_home, source_dir)
    install_config_examples(hermes_home, source_dir)
    install_tone_map(hermes_home, source_dir)

    print("🎉 安装完成！")
    print()
    print("下一步：")
    print("  1. 在 config.yaml 中启用插件：")
    print('     plugins:')
    print('       emotion-governor:')
    print('         enabled: true')
    print('       mode-switch:')
    print('         enabled: true')
    print("  2. 重启 Hermes Gateway: hermes gateway restart")
    print("  3. 参考 docs/ 了解情绪系统和各功能的使用方式")


if __name__ == "__main__":
    main()
