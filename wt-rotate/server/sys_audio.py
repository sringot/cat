import platform

_set_volume_fn = None


def _init():
    global _set_volume_fn
    if platform.system() != 'Windows':
        return
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL          # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

        def _fn(level: int) -> None:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            cast(interface, POINTER(IAudioEndpointVolume)).SetMasterVolumeLevelScalar(
                level / 100.0, None)

        _set_volume_fn = _fn
        print('[+] Volume système : pycaw actif')
    except ImportError:
        print('[i] Volume système : pip install pycaw pour le contrôle audio du système')
    except Exception as e:
        print(f'[!] Volume système non disponible : {e}')


_init()


def set_volume(level: int) -> bool:
    """Règle le volume maître Windows (0-100). Retourne True si succès."""
    if _set_volume_fn is None:
        return False
    try:
        _set_volume_fn(max(0, min(100, int(level))))
        return True
    except Exception:
        return False
