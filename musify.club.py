import requests
import re
import os
import time
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup
import argparse

class MusifyDownloader:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_tracks_from_page(self, url):
        """Получаем информацию о треках со страницы релиза"""
        print(f"[INFO] Загружаем страницу: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем все элементы с треками
            track_elements = soup.find_all('div', class_='playlist__item')
            
            if not track_elements:
                # Попробуем другой селектор
                track_elements = soup.find_all('div', id=re.compile(r'playerDiv\d+'))
            
            tracks = []
            
            for track in track_elements:
                # Получаем название трека
                track_name_elem = track.find('a', class_='strong')
                track_name = track_name_elem.text.strip() if track_name_elem else "Unknown"
                
                # Получаем артиста
                artist_elem = track.find('a', href=re.compile(r'/artist/'))
                artist = artist_elem.text.strip() if artist_elem else "Unknown"
                
                # Получаем прямую ссылку на MP3 из data-play-url
                play_button = track.find('div', class_='play')
                if play_button and play_button.has_attr('data-play-url'):
                    mp3_path = play_button['data-play-url']
                    
                    # Проверяем, доступен ли трек (нет класса noplay)
                    is_available = 'noplay' not in play_button.get('class', [])
                    
                    # Формируем полный URL
                    if mp3_path.startswith('/'):
                        mp3_url = urljoin('https://musify.club', mp3_path)
                    else:
                        mp3_url = mp3_path
                    
                    # Декодируем URL-encoded названия для читаемого имени файла
                    decoded_name = unquote(mp3_url.split('/')[-1]).replace('.mp3', '')
                    
                    tracks.append({
                        'artist': artist,
                        'name': track_name,
                        'url': mp3_url,
                        'filename': f"{artist} - {track_name}.mp3",
                        'available': is_available,
                        'decoded_name': decoded_name
                    })
                else:
                    # Если нет data-play-url, трек недоступен
                    tracks.append({
                        'artist': artist,
                        'name': track_name,
                        'url': None,
                        'filename': f"{artist} - {track_name}.mp3",
                        'available': False,
                        'decoded_name': None
                    })
            
            return tracks
            
        except Exception as e:
            print(f"[ERROR] Ошибка при получении данных: {e}")
            return []

    def sanitize_filename(self, filename):
        """Очищает имя файла от недопустимых символов"""
        # Заменяем недопустимые символы
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        # Удаляем лишние пробелы
        filename = ' '.join(filename.split())
        # Ограничиваем длину имени файла
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200] + ext
        return filename

    def download_track(self, track_info, folder='downloads'):
        """Скачивает один трек"""
        if not track_info['available'] or not track_info['url']:
            print(f"[SKIP] Трек '{track_info['name']}' недоступен для скачивания")
            return False
        
        # Создаем папку для загрузок
        if not os.path.exists(folder):
            os.makedirs(folder)
        
        # Очищаем имя файла
        safe_filename = self.sanitize_filename(track_info['filename'])
        filepath = os.path.join(folder, safe_filename)
        
        # Если файл уже существует, пропускаем
        if os.path.exists(filepath):
            print(f"[SKIP] Файл уже существует: {safe_filename}")
            return True
        
        print(f"[DOWNLOAD] Скачиваем: {track_info['artist']} - {track_info['name']}")
        
        try:
            # Добавляем Referer для обхода защиты
            headers = self.headers.copy()
            headers['Referer'] = 'https://musify.club/'
            headers['Accept'] = '*/*'
            
            response = self.session.get(
                track_info['url'], 
                headers=headers, 
                stream=True,
                timeout=60
            )
            response.raise_for_status()
            
            # Получаем размер файла
            total_size = int(response.headers.get('content-length', 0))
            
            # Скачиваем файл
            with open(filepath, 'wb') as f:
                if total_size == 0:
                    f.write(response.content)
                else:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            # Показываем прогресс для больших файлов
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"\r[PROGRESS] {percent:.1f}% ({downloaded/1024:.1f} KB/{total_size/1024:.1f} KB)", end='')
            
            print(f"\n[SUCCESS] Скачан: {safe_filename}")
            return True
            
        except Exception as e:
            print(f"\n[ERROR] Ошибка при скачивании {track_info['name']}: {e}")
            # Удаляем частично скачанный файл
            if os.path.exists(filepath):
                os.remove(filepath)
            return False

    def download_all_tracks(self, url, folder='downloads'):
        """Скачивает все треки с указанной страницы"""
        print("=" * 60)
        print("Musify.club Downloader")
        print("=" * 60)
        
        # Получаем информацию о треках
        tracks = self.get_tracks_from_page(url)
        
        if not tracks:
            print("[ERROR] Не удалось найти треки на странице")
            return
        
        # Фильтруем доступные треки
        available_tracks = [t for t in tracks if t['available'] and t['url']]
        unavailable_tracks = [t for t in tracks if not t['available'] or not t['url']]
        
        print(f"[INFO] Найдено треков: {len(tracks)}")
        print(f"[INFO] Доступно для скачивания: {len(available_tracks)}")
        print(f"[INFO] Недоступно: {len(unavailable_tracks)}")
        
        # Выводим список треков
        print("\n" + "=" * 60)
        print("Список треков:")
        print("=" * 60)
        
        for i, track in enumerate(tracks, 1):
            status = "✓" if track['available'] and track['url'] else "✗"
            print(f"{i:3}. [{status}] {track['artist']} - {track['name']}")
        
        if not available_tracks:
            print("\n[ERROR] Нет доступных треков для скачивания")
            return
        
        # Подтверждение скачивания
        print("\n" + "=" * 60)
        choice = input(f"Скачать {len(available_tracks)} доступных треков? (y/n): ").strip().lower()
        
        if choice != 'y':
            print("[INFO] Скачивание отменено")
            return
        
        # Скачиваем треки
        print("\n" + "=" * 60)
        print("Начинаю скачивание...")
        print("=" * 60)
        
        successful = 0
        failed = 0
        
        for i, track in enumerate(available_tracks, 1):
            print(f"\n[{i}/{len(available_tracks)}]")
            if self.download_track(track, folder):
                successful += 1
            else:
                failed += 1
            
            # Пауза между запросами, чтобы не перегружать сервер
            time.sleep(1)
        
        # Выводим статистику
        print("\n" + "=" * 60)
        print("СКАЧИВАНИЕ ЗАВЕРШЕНО!")
        print("=" * 60)
        print(f"Успешно: {successful} треков")
        print(f"Не удалось: {failed} треков")
        print(f"Недоступно: {len(unavailable_tracks)} треков")
        
        if unavailable_tracks:
            print("\nНедоступные треки:")
            for track in unavailable_tracks:
                print(f"  - {track['artist']} - {track['name']}")
        
        print(f"\nВсе файлы сохранены в папке: {os.path.abspath(folder)}")

def main():
    parser = argparse.ArgumentParser(description='Скачиватель треков с Musify.club')
    parser.add_argument('url', help='URL страницы релиза на Musify.club')
    parser.add_argument('--folder', '-f', default='downloads', help='Папка для сохранения (по умолчанию: downloads)')
    
    args = parser.parse_args()
    
    downloader = MusifyDownloader()
    downloader.download_all_tracks(args.url, args.folder)

if __name__ == "__main__":
    main()
