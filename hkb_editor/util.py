from __future__ import annotations
import math


def euler_to_quat(
    roll: float, pitch: float, yaw: float
) -> tuple[float, float, float, float]:
    """
    Convert Roll-Pitch-Yaw (XYZ intrinsic) to quaternion (x, y, z, w).
    Angles in radians.
    """
    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)

    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy

    # normalize (robust to small drift)
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n == 0.0:
        raise ValueError("Inputs resulted in zero-norm quaternion")

    return (x / n, y / n, z / n, w / n)


def quat_to_euler(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    """
    Convert quaternion (x, y, z, w) to Roll-Pitch-Yaw (XYZ intrinsic).
    Returns (roll, pitch, yaw) in radians.
    """
    # normalize first
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n == 0.0:
        raise ValueError("Zero-norm quaternion")

    x, y, z, w = x / n, y / n, z / n, w / n

    # roll (x-axis rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # pitch (y-axis rotation)
    sinp = 2.0 * (w * y - z * x)
    if sinp <= -1.0:
        pitch = -math.pi / 2
    elif sinp >= 1.0:
        pitch = math.pi / 2
    else:
        pitch = math.asin(sinp)

    # yaw (z-axis rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return (roll, pitch, yaw)
