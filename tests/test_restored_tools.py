"""测试恢复后的 5 个工具：install_pip, read_csv, image_info, compress_image, text_to_speech"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(__file__))

from tools.dispatcher import execute_tool

async def main():
    print("=" * 60)
    print("测试恢复的工具")
    print("=" * 60)

    results = {}

    # 1. install_pip - 检查 pip 是否可用
    print("\n1. install_pip...")
    r = await execute_tool("install_pip", {"package": "--version"})
    print(f"   结果: {r[:100]}")
    results["install_pip"] = "pip" in r.lower() or "error" not in r.lower()

    # 2. read_csv - 创建一个测试 CSV
    print("\n2. read_csv...")
    test_csv = "F:/工具/测试/test_tool_csv.csv"
    with open(test_csv, "w", encoding="utf-8") as f:
        f.write("name,age,city\nAlice,30,NYC\nBob,25,LA\nCharlie,35,SF")
    r = await execute_tool("read_csv", {"path": test_csv, "n": 3})
    print(f"   结果: {r[:150]}")
    results["read_csv"] = "Alice" in r or "name" in r
    os.remove(test_csv)

    # 3. image_info - 需要一个测试图片
    print("\n3. image_info...")
    # 用现有图片测试
    test_img = "F:/工具/Agent_maona/renderer/icons/icon.png"
    if os.path.exists(test_img):
        r = await execute_tool("image_info", {"path": test_img})
        print(f"   结果: {r[:150]}")
        results["image_info"] = "尺寸" in r or "size" in r.lower() or "width" in r.lower()
    else:
        print("   跳过：无测试图片")
        results["image_info"] = None

    # 4. compress_image - 需要测试图片
    print("\n4. compress_image...")
    if os.path.exists(test_img):
        out_path = "F:/工具/测试/test_compressed.png"
        r = await execute_tool("compress_image", {"path": test_img, "width": 64, "output": out_path})
        print(f"   结果: {r[:150]}")
        results["compress_image"] = os.path.exists(out_path) or "成功" in r or "saved" in r.lower()
        if os.path.exists(out_path):
            os.remove(out_path)
    else:
        print("   跳过：无测试图片")
        results["compress_image"] = None

    # 5. text_to_speech
    print("\n5. text_to_speech...")
    r = await execute_tool("text_to_speech", {"text": "测试语音合成", "lang": "zh"})
    print(f"   结果: {r[:150]}")
    results["text_to_speech"] = "语音" in r or "朗读" in r or "speak" in r.lower() or "TTS" in r

    # 总结
    print("\n" + "=" * 60)
    print("测试结果:")
    print("=" * 60)
    for name, ok in results.items():
        status = "✅ 通过" if ok else ("❌ 失败" if ok is False else "⏭️ 跳过")
        print(f"  {name}: {status}")

    passed = sum(1 for v in results.values() if v is True)
    total = sum(1 for v in results.values() if v is not None)
    print(f"\n总计: {passed}/{total} 通过")
    return passed == total

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
