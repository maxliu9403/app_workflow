"""
inject_metadata.py - Deep Image Wash & EXIF Injection Tool (终极版 V3.2)

功能：
1. 深度视觉清洗 (Deep Wash++) - 亮度通道噪点注入
2. 完整相机 EXIF 参数注入 - 光圈、ISO、快门、焦距等
3. Android 命名规范 - IMG_YYYYMMDD_HHMMSS.jpg
4. ADB 自动推送到设备相册
5. 文件时间戳同步 (Timestamp Sync)

V3.0 核心特性（保留）：
- 深度元数据清洗 (全新像素复制，移除 XMP/ICC)
- JPEG 压缩指纹随机化 (92-98 质量随机)
- EXIF 缩略图安全处理 (强制移除)
- 亮度通道噪点 (Luma-only noise，避免彩色噪点)

V3.1 工程化修复：
- 修复中文路径 ADB 支持 (Raw String)
- 智能 ADB 路径检测与回退
- 文件系统时间戳同步 (os.utime)
- 增强版推送与逐文件媒体扫描

V3.2 终极优化：
- 自然排序 (Natural Sort): 1, 2, 10 而非 1, 10, 2
- 固定时间间隔 (1分钟/张): 确保相册顺序严格正确
- 严格顺序控制: 第1张时间最早，最后1张时间最晚

作者：Automation Team
"""

import os
import sys
import subprocess
import random
import shutil
import re
import time as time_module
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List
from pathlib import Path

# Third-party libraries
try:
    from PIL import Image, ImageEnhance, ImageCms
    import numpy as np
    import piexif
except ImportError:
    print("❌ Error: Missing dependencies. Please run: pip install Pillow piexif numpy")
    sys.exit(1)


# ================= V3.1: ADB 路径智能检测 =================

# 硬编码的中文路径（使用 Raw String 防止转义错误）
PRIMARY_ADB_PATH = r"D:\桌面\platform-tools\adb.exe"

def get_adb_command() -> str:
    """
    V3.1: 智能获取 ADB 命令路径
    
    优先级：
    1. 硬编码路径 D:\\桌面\\platform-tools\\adb.exe
    2. 系统环境变量中的 adb
    3. 报错并提供安装指引
    """
    # 1. 检测硬编码的中文路径
    if os.path.exists(PRIMARY_ADB_PATH):
        print(f"✅ 使用指定 ADB: {PRIMARY_ADB_PATH}")
        return f'"{PRIMARY_ADB_PATH}"'  # 带引号处理空格/特殊字符
    
    # 2. 尝试从系统 PATH 中获取
    try:
        if os.name == 'nt':
            result = subprocess.run(["where", "adb"], capture_output=True, text=True, timeout=5)
        else:
            result = subprocess.run(["which", "adb"], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            found_path = result.stdout.strip().split('\n')[0]
            if os.path.exists(found_path):
                print(f"✅ 系统环境 ADB: {found_path}")
                return f'"{found_path}"'
    except Exception:
        pass
    
    # 3. 尝试直接使用 adb（假设在 PATH 中）
    try:
        result = subprocess.run(["adb", "version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            print("✅ 使用系统 PATH 中的 adb")
            return "adb"
    except Exception:
        pass
    
    # 4. 报错并提供指引
    print("=" * 60)
    print("❌ [FATAL] 未找到 ADB 可执行文件！")
    print("=" * 60)
    print("请执行以下操作之一：")
    print(f"  1. 将 platform-tools 放置到: {PRIMARY_ADB_PATH}")
    print("  2. 或将 platform-tools 目录添加到系统 PATH 环境变量")
    print("  3. 下载地址: https://developer.android.com/tools/releases/platform-tools")
    print("=" * 60)
    sys.exit(1)


# 初始化 ADB 命令
ADB_CMD = get_adb_command()
CONFIG_PATH = "/data/local/tmp/multiapp_conf.txt"
DEVICE_DCIM_PATH = "/sdcard/DCIM/Camera/"


# ================= V3.1: ADB 命令执行 =================

def run_adb_command(cmd: str, timeout: int = 30, use_root: bool = False) -> str:
    """
    执行 ADB 命令并返回输出
    
    Args:
        cmd: ADB 子命令（不含 adb 前缀）
        timeout: 超时秒数
        use_root: 是否使用 su -c 包装命令（用于读取 Root 文件）
    """
    try:
        if use_root and cmd.startswith("shell "):
            # 提取 shell 后面的实际命令并用 su -c 包装
            shell_cmd = cmd[6:]  # 去掉 "shell " 前缀
            full_cmd = f'{ADB_CMD} shell "su -c \'{shell_cmd}\'"'
        else:
            full_cmd = f"{ADB_CMD} {cmd}"
        
        result = subprocess.run(
            full_cmd, 
            shell=True, 
            capture_output=True, 
            timeout=timeout
        )
        
        if result.returncode != 0:
            # 尝试获取错误信息
            stderr = result.stderr.decode('utf-8', errors='ignore').strip()
            if stderr:
                return ""
            return ""
        
        raw_output = result.stdout
        
        # 多编码尝试解码
        for encoding in ['utf-8', 'gbk', 'mbcs']:
            try:
                return raw_output.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        
        return raw_output.decode('utf-8', errors='ignore').strip()
        
    except subprocess.TimeoutExpired:
        print(f"⚠️ ADB 命令超时 ({timeout}s): {cmd[:50]}...")
        return ""
    except Exception as e:
        print(f"⚠️ ADB 执行错误: {e}")
        return ""


def get_device_config() -> Dict[str, str]:
    """
    从手机读取当前活跃的配置文件
    V3.1: 支持 Root 权限读取
    """
    print("📱 连接设备读取配置...")
    
    # 检测设备连接
    res = run_adb_command("shell echo connected")
    if "connected" not in res:
        print("❌ Error: 未检测到 Android 设备或未授权 USB 调试")
        print("   请检查：")
        print("   1. 手机是否通过 USB 连接")
        print("   2. USB 调试是否已开启")
        print("   3. 是否已在手机上授权此电脑")
        sys.exit(1)
    
    # 尝试普通读取
    content = run_adb_command(f"shell cat {CONFIG_PATH}")
    
    # 如果普通读取失败，尝试 Root 读取
    if not content or "No such file" in content or "Permission denied" in content:
        print("⚠️ 普通权限读取失败，尝试 Root 读取...")
        content = run_adb_command(f"shell cat {CONFIG_PATH}", use_root=True)
    
    if not content or "No such file" in content:
        print(f"❌ Error: 配置文件不存在: {CONFIG_PATH}")
        print("   请确保已运行 vm.sh 初始化环境")
        sys.exit(1)

    config = {}
    for line in content.splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            config[key.strip()] = val.strip()
    
    model = config.get('MODEL', 'Unknown')
    gps_lat = config.get('GPS_LAT', 'N/A')
    gps_lon = config.get('GPS_LON', 'N/A')
    print(f"✅ 已加载配置: {model} | GPS: {gps_lat}, {gps_lon}")
    return config


# ================= 坐标转换 =================

def dec_to_dms(deg: float, is_lat: bool) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    """将十进制坐标转换为 EXIF 有理数格式 (度, 分, 秒)"""
    abs_deg = abs(deg)
    d = int(abs_deg)
    m = int((abs_deg - d) * 60)
    s = int((abs_deg - d - m / 60) * 3600 * 100)
    return ((d, 1), (m, 1), (s, 100))


# ================= V3.0: 深度元数据清洗 =================

def strip_all_metadata(image: Image.Image) -> Image.Image:
    """创建全新的无元数据图像对象，仅复制像素数据"""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    clean_image = Image.new('RGB', image.size)
    clean_image.paste(image, (0, 0))
    return clean_image


def convert_to_srgb(image: Image.Image) -> Image.Image:
    """将图像转换为标准 sRGB 色彩空间"""
    try:
        icc_profile = image.info.get('icc_profile')
        if icc_profile:
            srgb_profile = ImageCms.createProfile('sRGB')
            try:
                src_profile = ImageCms.ImageCmsProfile(icc_profile)
                image = ImageCms.profileToProfile(
                    image, src_profile, srgb_profile,
                    renderingIntent=ImageCms.Intent.PERCEPTUAL,
                    outputMode='RGB'
                )
            except Exception:
                pass
    except Exception:
        pass
    return image


# ================= V3.0: 亮度通道噪点注入 =================

def apply_luma_noise(image: Image.Image, intensity: float = 0.015) -> Image.Image:
    """
    亮度通道高斯噪点注入（Human-Eye Friendly）
    仅在 Y（亮度）通道添加噪点，避免彩色杂点
    """
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # 转换到 YCbCr 色彩空间
    ycbcr = image.convert('YCbCr')
    y_channel, cb_channel, cr_channel = ycbcr.split()
    
    # 仅对 Y 通道添加噪点
    y_array = np.array(y_channel, dtype=np.float32)
    noise_sigma = 255.0 * intensity * random.uniform(0.8, 1.2)
    noise = np.random.normal(loc=0, scale=noise_sigma, size=y_array.shape)
    y_noisy = np.clip(y_array + noise, 0, 255).astype(np.uint8)
    
    # 重建并转回 RGB
    y_channel_noisy = Image.fromarray(y_noisy, mode='L')
    ycbcr_noisy = Image.merge('YCbCr', (y_channel_noisy, cb_channel, cr_channel))
    return ycbcr_noisy.convert('RGB')


def apply_deep_wash(image: Image.Image) -> Image.Image:
    """
    深度视觉清洗 (Deep Wash++ V3.0)
    微旋转 + 边缘裁剪 + 亮度噪点 + 光度变换
    """
    width, height = image.size
    
    # 1. 微旋转
    angle = random.uniform(0.5, 1.5) * random.choice([-1, 1])
    image = image.rotate(angle, resample=Image.BICUBIC, expand=True)
    
    # 2. 边缘裁剪 6-8%
    w_new, h_new = image.size
    crop_factor = random.uniform(0.06, 0.08)
    left = int(w_new * crop_factor)
    top = int(h_new * crop_factor)
    image = image.crop((left, top, w_new - left, h_new - top))
    image = image.resize((width, height), Image.LANCZOS)
    
    # 3. 亮度通道噪点
    noise_intensity = random.uniform(0.010, 0.018)
    image = apply_luma_noise(image, intensity=noise_intensity)
    
    # 4. 光度变换
    for enhance_cls, low, high in [
        (ImageEnhance.Brightness, 0.95, 1.05),
        (ImageEnhance.Contrast, 0.95, 1.05),
        (ImageEnhance.Color, 0.97, 1.03),
    ]:
        image = enhance_cls(image).enhance(random.uniform(low, high))
    
    return image


# ================= EXIF 生成 =================

def generate_camera_exif(config: Dict[str, str], photo_time: datetime, 
                         lat: Optional[float], lon: Optional[float], alt: float) -> bytes:
    """生成完整的相机 EXIF 数据"""
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    
    # 设备信息
    exif_dict["0th"][piexif.ImageIFD.Make] = config.get("MANUFACTURER", "Xiaomi")
    exif_dict["0th"][piexif.ImageIFD.Model] = config.get("MODEL", "M2012K11AG")
    exif_dict["0th"][piexif.ImageIFD.Software] = f"Android {config.get('ro.build.version.release', '13')}"
    
    # 时间信息
    time_str = photo_time.strftime("%Y:%m:%d %H:%M:%S")
    exif_dict["0th"][piexif.ImageIFD.DateTime] = time_str
    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = time_str
    exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = time_str
    
    # 光学参数
    fnumber = random.choice([1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.4])
    exif_dict["Exif"][piexif.ExifIFD.FNumber] = (int(fnumber * 10), 10)
    exif_dict["Exif"][piexif.ExifIFD.ApertureValue] = (int(fnumber * 10), 10)
    
    iso = random.choice([50, 64, 80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800])
    exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings] = iso
    
    shutter_denom = random.choice([50, 60, 80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600, 2000])
    exif_dict["Exif"][piexif.ExifIFD.ExposureTime] = (1, shutter_denom)
    
    focal_length = random.choice([24.0, 25.0, 26.0, 27.0, 28.0])
    exif_dict["Exif"][piexif.ExifIFD.FocalLength] = (int(focal_length * 10), 10)
    exif_dict["Exif"][piexif.ExifIFD.FocalLengthIn35mmFilm] = int(focal_length)
    
    exif_dict["Exif"][piexif.ExifIFD.WhiteBalance] = 0
    exif_dict["Exif"][piexif.ExifIFD.ExposureMode] = 0
    exif_dict["Exif"][piexif.ExifIFD.MeteringMode] = random.choice([2, 5])
    exif_dict["Exif"][piexif.ExifIFD.Flash] = 0
    exif_dict["Exif"][piexif.ExifIFD.ColorSpace] = 1
    
    # GPS 信息
    if lat is not None and lon is not None:
        lat_ref = b'N' if lat >= 0 else b'S'
        lon_ref = b'E' if lon >= 0 else b'W'
        alt_ref = 0 if alt >= 0 else 1
        
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = lat_ref
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = dec_to_dms(lat, True)
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = lon_ref
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = dec_to_dms(lon, False)
        exif_dict["GPS"][piexif.GPSIFD.GPSAltitudeRef] = alt_ref
        exif_dict["GPS"][piexif.GPSIFD.GPSAltitude] = (int(abs(alt) * 100), 100)
        
        gps_time = ((photo_time.hour, 1), (photo_time.minute, 1), (photo_time.second, 1))
        exif_dict["GPS"][piexif.GPSIFD.GPSTimeStamp] = gps_time
        exif_dict["GPS"][piexif.GPSIFD.GPSDateStamp] = photo_time.strftime("%Y:%m:%d")
    
    return piexif.dump(exif_dict)


def generate_android_filename(photo_time: datetime) -> str:
    """生成 Android 原生相机命名格式: IMG_YYYYMMDD_HHMMSS.jpg"""
    return f"IMG_{photo_time.strftime('%Y%m%d_%H%M%S')}.jpg"


# ================= V3.1: 增强版推送与扫描 =================

def push_to_device(output_folder: str) -> bool:
    """
    V3.1: 将处理后的图片推送到设备并逐文件触发媒体扫描
    """
    print("\n📤 正在推送图片到设备...")
    
    jpg_files = [f for f in os.listdir(output_folder) if f.lower().endswith('.jpg')]
    if not jpg_files:
        print("⚠️ 没有找到可推送的图片")
        return False
    
    # 确保目标目录存在
    run_adb_command(f"shell mkdir -p {DEVICE_DCIM_PATH}")
    
    success_count = 0
    pushed_files = []
    
    for filename in jpg_files:
        src_path = os.path.join(output_folder, filename)
        dst_path = f"{DEVICE_DCIM_PATH}{filename}"
        
        # 使用引号包装路径以处理特殊字符
        result = run_adb_command(f'push "{src_path}" "{dst_path}"', timeout=60)
        
        if "pushed" in result.lower() or "1 file" in result.lower() or result == "":
            # 验证文件是否存在
            check = run_adb_command(f'shell "[ -f \\"{dst_path}\\" ] && echo exists"')
            if "exists" in check:
                success_count += 1
                pushed_files.append(filename)
                print(f"  ✅ {filename}")
            else:
                print(f"  ⚠️ {filename}: 推送可能失败，无法验证")
        else:
            print(f"  ❌ {filename}: {result[:50]}...")
    
    print(f"\n📱 推送结果: {success_count}/{len(jpg_files)} 成功")
    
    # V3.1: 逐文件触发媒体扫描
    if pushed_files:
        print("🔄 触发媒体库扫描...")
        
        for filename in pushed_files:
            file_path = f"{DEVICE_DCIM_PATH}{filename}"
            scan_cmd = f'shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://{file_path}"'
            run_adb_command(scan_cmd)
        
        # 额外：扫描整个 Camera 目录
        run_adb_command(f'shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://{DEVICE_DCIM_PATH}"')
        
        print("✅ 媒体库扫描完成")
    
    return success_count > 0


# ================= V3.1: 文件时间戳同步 =================

def sync_file_timestamp(file_path: str, target_time: datetime) -> None:
    """
    V3.1: 将文件的访问时间和修改时间同步为目标时间
    
    Args:
        file_path: 文件绝对路径
        target_time: 目标时间（与 EXIF 拍摄时间一致）
    """
    try:
        # 转换 datetime 为 Unix 时间戳
        timestamp = target_time.timestamp()
        
        # 设置文件的访问时间和修改时间
        os.utime(file_path, (timestamp, timestamp))
        
    except Exception as e:
        print(f"  ⚠️ 时间戳同步失败: {e}")


# ================= 主处理逻辑 =================

def process_images(source_folder: str, config: Dict[str, str], auto_push: bool = True):
    """主处理逻辑 (V3.1 工程化版)"""
    if not os.path.exists(source_folder):
        print(f"❌ Error: 文件夹不存在: '{source_folder}'")
        sys.exit(1)

    # 1. 准备输出目录
    account_name = config.get("AccountName", "UnknownUser")
    model_name = config.get("MODEL", "Phone")
    output_folder = os.path.join(source_folder, f"Washed_{account_name}_{model_name}")
    
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
    os.makedirs(output_folder)
    
    print(f"📂 输出目录: {output_folder}")

    # 2. 时间逻辑
    days_ago = random.randint(1, 3)
    start_hour = random.randint(8, 17)
    base_time = datetime.now() - timedelta(days=days_ago)
    base_time = base_time.replace(hour=start_hour, minute=random.randint(0, 59), second=0, microsecond=0)
    
    print(f"🕒 拍摄时间起点: {base_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 3. GPS 数据解析
    lat, lon, alt = None, None, 10.0
    try:
        lat = float(config.get("GPS_LAT", "0.0"))
        lon = float(config.get("GPS_LON", "0.0"))
        alt = float(config.get("GPS_ALT", "10.0"))
        print(f"📍 GPS: {lat:.6f}, {lon:.6f}, Alt: {alt:.1f}m")
    except ValueError:
        print("⚠️ GPS 数据无效，跳过 GPS 注入")
        lat = None

    # 4. V3.2: 自然排序 (Natural Sort)
    # 确保 1.jpg, 2.jpg, 10.jpg 而不是 1, 10, 2
    def natural_sort_key(s: str):
        """提取字符串中的数字进行自然排序"""
        return [int(text) if text.isdigit() else text.lower() 
                for text in re.split(r'(\d+)', s)]
    
    valid_exts = {'.jpg', '.jpeg', '.png', '.webp'}
    files = [f for f in os.listdir(source_folder) 
             if os.path.splitext(f)[1].lower() in valid_exts 
             and not f.startswith('.')
             and os.path.isfile(os.path.join(source_folder, f))]
    
    # V3.2: 使用自然排序
    files.sort(key=natural_sort_key)
    
    if not files:
        print("❌ 未找到有效的图片文件")
        return
    
    print(f"📷 找到 {len(files)} 张图片（自然排序）")
    print(f"   排序预览: {files[:3]}{'...' if len(files) > 3 else ''}\n")
    
    processed_count = 0
    
    for i, filename in enumerate(files):
        src_path = os.path.join(source_folder, filename)
        
        try:
            # 加载并清洗元数据
            original_img = Image.open(src_path)
            original_img = convert_to_srgb(original_img)
            original_img = original_img.convert('RGB')
            img = strip_all_metadata(original_img)
            original_img.close()
            
            # V3.2: 固定时间间隔（每张 +1 分钟）
            # 确保相册按时间排序时顺序严格正确
            photo_time = base_time + timedelta(minutes=i)
            
            # 生成文件名和路径
            new_filename = generate_android_filename(photo_time)
            dst_path = os.path.join(output_folder, new_filename)
            
            # 深度清洗
            img = apply_deep_wash(img)
            
            # 生成 EXIF
            exif_bytes = generate_camera_exif(config, photo_time, lat, lon, alt)
            
            # 随机压缩质量
            jpeg_quality = random.randint(92, 98)
            
            # 保存图片
            img.save(
                dst_path, 
                "JPEG", 
                exif=exif_bytes, 
                quality=jpeg_quality,
                subsampling=0,
                optimize=True
            )
            
            # V3.1: 同步文件系统时间戳
            sync_file_timestamp(dst_path, photo_time)
            
            processed_count += 1
            time_str = photo_time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"✅ [{processed_count:3d}] {filename} -> {new_filename} | {time_str} | Q{jpeg_quality}")
            
        except Exception as e:
            print(f"❌ Failed: {filename}: {e}")

    print(f"\n🎉 处理完成! {processed_count} 张图片已保存到:\n{output_folder}")
    
    # 5. 自动推送到设备
    if auto_push and processed_count > 0:
        push_to_device(output_folder)


# ================= 入口点 =================

if __name__ == "__main__":
    print("=" * 60)
    print("📸 Image Deep Wash & EXIF Injection Tool v3.1 (工程化版)")
    print("=" * 60)
    
    if len(sys.argv) < 2:
        print("\n用法: python inject_metadata.py <图片文件夹路径> [--no-push]")
        print("示例: python inject_metadata.py D:\\Photos\\Shoes_Batch1")
        print("选项: --no-push  不自动推送到设备")
        sys.exit(1)
    
    target_folder = sys.argv[1]
    auto_push = "--no-push" not in sys.argv
    
    # 获取设备配置
    conf = get_device_config()
    
    # 处理图片
    process_images(target_folder, conf, auto_push=auto_push)
