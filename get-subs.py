#!/usr/bin/python3

# Copyright 2016-2018 Juan Orti Alcaine <j.orti.alcaine@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import os
import argparse
import subprocess
from subliminal import scan_video, download_best_subtitles, save_subtitles
import babelfish
import json
import logging


class Video:
    def __init__(self, file_path):
        self.path = os.path.abspath(file_path)
        (self.directory, self.filename) = os.path.split(self.path)
        (self.basename, self.extension) = os.path.splitext(self.filename)
        self.info = self._scan_video()
        (self.has_embedded_sub, self.embedded_sub_id) = self._scan_embedded_subtitles()

    def _scan_video(self):
        command = ["ffprobe", "-show_format", "-show_streams", "-loglevel", "quiet", "-print_format", "json",
                   self.path]
        logging.debug("Running command {}".format(command))
        info_json = subprocess.check_output(command)
        return json.loads(info_json.decode('utf_8'))

    def _scan_embedded_subtitles(self):
        for stream in self.info['streams']:
            if stream['codec_type'] == 'subtitle' and stream['codec_name'] == 'subrip':
                return True, stream['index']
        return False, None

    def has_external_subtitles(self):
        if os.path.isfile(os.path.join(self.directory, self.basename + ".srt")):
            return True
        return False

    def get_subtitles(self, force_download=False, lang='eng'):
        if not self.has_external_subtitles():
            if force_download:
                self.download_sub(lang)
            elif self.has_embedded_sub:
                self.extract_embedded_sub()
            else:
                self.download_sub(lang)

    def download_sub(self, lang):
        logging.info("{}: Downloading subtitles...".format(self.filename))
        vid = scan_video(self.path)
        best_subs = download_best_subtitles({vid}, {babelfish.Language(lang)}, only_one=True)
        if best_subs[vid]:
            sub = best_subs[vid][0]
            save_subtitles(vid, [sub], single=True)
            logging.info("{}: Subtitles successfully downloaded.".format(self.filename))
        else:
            logging.error("{}: No subtitles found online.".format(self.filename))

    def extract_embedded_sub(self):
        logging.info("{}: Extracting embedded subtitles...".format(self.filename))
        sub_path = os.path.join(self.directory, self.basename + '.srt')
        command = ["mkvextract", "tracks", self.path, str(self.embedded_sub_id) + ":" + sub_path]
        logging.debug("Running command {}".format(command))
        retval = subprocess.call(command)
        if retval == 0:
            logging.info("{}: Embedded subtitles successfully extracted.".format(self.filename))
        else:
            logging.error("{}: Embedded subtitles failed to extract.".format(self.filename))


def is_supported_video_file(file):
    supported_extensions = frozenset(['.mkv', '.mp4', '.avi', '.mpg', '.mpeg', '.divx'])
    if os.path.isfile(file):
        (basename, ext) = os.path.splitext(file)
        if ext in supported_extensions:
            return True
    logging.debug("Ignoring file: " + file)
    return False


def search_videos(directory, files):
    """Scan a directory for supported video files"""
    if not directory and not files:
        raise ValueError("A directory or a file must be specified")
    if directory:
        for root, dirs, files in os.walk(directory):
            for name in files:
                f = os.path.join(root, name)
                if is_supported_video_file(f):
                    yield Video(f)
    if files:
        for f in files:
            if is_supported_video_file(f):
                yield Video(f)


parser = argparse.ArgumentParser(
    description='Script to get video subtitles')
parser.add_argument("-d", "--directory",
                    help="Directory to scan recursively for videos")
parser.add_argument("--log-level", default="WARNING", help="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
parser.add_argument("-ds", "--download-subtitles", action="store_true",
                    help="Force to download subtitles")
parser.add_argument("-l", "--language", help="Subtitles language",
                    default="eng")
parser.add_argument("file", nargs='*', help="Files to analyze")
args = parser.parse_args()
logging.basicConfig(level=args.log_level.upper())
for v in search_videos(directory=args.directory, files=args.file):
    logging.info("{}: Processing file".format(v.filename))
    v.get_subtitles(force_download=args.download_subtitles, lang=args.language)
