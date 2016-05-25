#!/usr/bin/env python3
"""
Copyright 2016 Juan Orti Alcaine <j.orti.alcaine@gmail.com>


This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sys
import os
import argparse
import subprocess
import re
import pprint
import subliminal
import babelfish

#for i in *mkv; do ffmpeg -i $i -c:v libx264 -preset slow -acodec copy -scodec copy h264-$i; done

class Video:
    def __init__(self, file_path):
        self.path = os.path.abspath(file_path)
        (self.directory, self.filename) = os.path.split(self.path)
        (self.basename, self.extension) = os.path.splitext(self.filename)
        self._scan_subtitles()

    def _scan_subtitles(self):
        if self.extension == ".mkv":
            try:
                raw_info = subprocess.check_output(["mkvmerge", "-i", self.path],
                                            stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as ex:
                print(ex)
                sys.exit(1)
            pattern = re.compile('.* (\d+): subtitles \(SubRip/SRT\).*', re.DOTALL)
            m = pattern.match(str(raw_info))
            if m:
                self.has_embedded_sub = True
                self.embedded_sub_id = m.group(1)
            else:
                self.has_embedded_sub = False
        else:
            self.has_embedded_sub = False
        self.sub_path = os.path.join(self.directory, self.basename + ".srt")
        if os.path.isfile(self.sub_path):
            self.has_external_sub = True
        else:
            self.has_external_sub = False


def extract_embedded_sub(video):
    print("Extracting embedded subtitles for {f}".format(f=video.filename))
    try:
        subprocess.call(["mkvextract", "tracks", video.path,
                         video.embedded_sub_id + ":" + video.sub_path])
        print("OK.")
    except subprocess.CalledProcessError:
        print("ERROR.")


def download_sub(video):
    print("Downloading subtitles for {f}".format(f=video.filename))
    try:
        v = subliminal.scan_video(video.path)
    except ValueError as ex:
        print("ERROR: Failed to analyze video video file. ", ex)
    best_subs = subliminal.download_best_subtitles({v},
            {babelfish.Language('eng')}, only_one=True)
    if best_subs[v]:
        sub = best_subs[v][0]
        subliminal.save_subtitles(v, [sub], single=True)
        print("OK.")
    else:
        print("ERROR: No subtitles found online.")



def get_subtitles(video):
    if not video.has_external_sub:
        if video.has_embedded_sub:
            extract_embedded_sub(video)
        else:
            download_sub(video)
    else:
        print("Subtitles OK for {f}".format(f=video.filename))

def scan_videos(dir):
    "Scan a directory for supported video files"
    supported_extensions = {'.mkv', '.mp4', '.avi', '.mpg', '.mpeg'}
    videos = []
    for root, dirs, files in os.walk(dir):
        for name in files:
            (basename, ext) = os.path.splitext(name)
            if ext in supported_extensions:
                v = Video(os.path.join(root, name))
                videos.append(v)
    return videos


def main(argv):
    parser = argparse.ArgumentParser(description="Prepare videos for LG TV")
    parser.add_argument("-d", "--directory", help="Directory to scan for videos",
                        default=".")
    parser.add_argument("-p", "--prefix", help="Converted files prefix",
                        default="lgtv")
    args = parser.parse_args()
    videos = scan_videos(args.directory)
    for v in videos:
        get_subtitles(v)
    #for v in videos:
    #    pprint.pprint(v.__dict__)


if __name__ == '__main__':
    main(sys.argv)
