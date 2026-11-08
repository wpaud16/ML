"""브리핑관리.exe 빌드 (PyInstaller, 표준 라이브러리만 쓰는 briefing_app.py 를 한 파일로).
  python local_runner/build_app.py   → local_runner/dist/브리핑관리.exe (저장소에 올려 다른 PC 에서 내려받기) + 설치 폴더에 복사"""
import os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.dirname(os.path.dirname(HERE))
NAME = '브리핑관리'
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--disable-pip-version-check', 'pyinstaller'], check=True)
work = os.path.join(os.environ.get('TEMP', HERE), 'briefing_build')
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed', '--name', NAME,
                '--distpath', os.path.join(HERE, 'dist'), '--workpath', work, '--specpath', work,
                os.path.join(HERE, 'briefing_app.py')], check=True)
exe = os.path.join(HERE, 'dist', NAME + '.exe')
shutil.copy2(exe, os.path.join(HOME, NAME + '.exe'))
print('빌드:', exe, f'{os.path.getsize(exe) / 1e6:.1f}MB', '→ 복사:', os.path.join(HOME, NAME + '.exe'))
