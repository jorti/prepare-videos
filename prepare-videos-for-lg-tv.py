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
import subliminal
import babelfish
import json


class Video:
    def __init__(self, file_path):
        self.path = os.path.abspath(file_path)
        (self.directory, self.filename) = os.path.split(self.path)
        (self.basename, self.extension) = os.path.splitext(self.filename)
        self._scan_video()
        self._scan_subtitles()

    def _scan_video(self):
        try:
            info_json = subprocess.check_output(["ffprobe", "-show_format",
                "-show_streams", "-loglevel", "quiet", "-print_format", "json",
                self.path])
        except subprocess.CalledProcessError as ex:
            print(ex)
            sys.exit(1)
        self.info = json.loads(info_json.decode('utf_8'))

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

def transcode_video(video, prefix):
    unsupported_video_codecs = {'hevc'}
    unsupported_audio_codecs = {'dts', 'dca'}
    target = os.path.join(video.directory, prefix + "-" + video.filename)
    if os.path.isfile(target):
        print("Skipping already converted video {f}".format(f=video.filename))
        return
    supported_video_codec = True
    supported_audio_codec = True
    for stream in video.info['streams']:
        if stream['codec_type'] == "video" and \
                stream['codec_name'] in unsupported_video_codecs:
            print("Unsupported video codec {c} in file {f}".format(c=stream['codec_name'],
                f=video.filename))
            supported_video_codec = False
        if stream['codec_type'] == "audio" and \
                stream['codec_name'] in unsupported_audio_codecs:
            print("Unsupported audio codec {c} in file {f}".format(c=stream['codec_name'],
                f=video.filename))
            supported_audio_codec = False
    if not supported_video_codec or not supported_audio_codec:
        #ffmpeg -i file -nostats -loglevel 0 -c:v libx264 -preset slow -acodec copy -scodec copy h264-file
        command = ["ffmpeg", "-i", video.path, "-nostats", "-loglevel", "0"]
        if not supported_video_codec:
            command += ["-c:v", "libx264", "-preset", "slow"]
        else:
            command += ["-vcodec", "copy"]
        if not supported_audio_codec:
            command += ["-c:a", "ac3"]
        else:
            command += ["-acodec", "copy"]
        command += ["-scodec", "copy", target]
        print("Running command: {c}".format(c=command))
        try:
            subprocess.call(command)
            print("OK: Video {f} transcoded".format(f=video.filename))
        except subprocess.CalledProcessError:
            print("ERROR: Video {f} failed to transcode".format(f=video.filename))
        new_video = Video(target)
        get_subtitles(new_video)


def is_supported_video_file(file):
    supported_extensions = {'.mkv', '.mp4', '.avi', '.mpg', '.mpeg'}
    if os.path.isfile(file):
        (basename, ext) = os.path.splitext(file)
        if ext in supported_extensions:
            return True
    return False

def scan_videos(dir=None, file_list=None):
    "Scan a directory for supported video files"
    if not dir and not file_list:
        raise ValueError("A directory or a file must be specified")
    supported_extensions = {'.mkv', '.mp4', '.avi', '.mpg', '.mpeg'}
    videos = []
    if dir:
        for root, dirs, files in os.walk(dir):
            for name in files:
                f = os.path.join(root, name)
                if is_supported_video_file(f):
                    videos.append(Video(f))
    if file_list:
        for f in file_list:
            if is_supported_video_file(f):
                videos.append(Video(f))
    return videos


def main(argv):
    parser = argparse.ArgumentParser(description="Prepare videos for LG TV")
    parser.add_argument("-d", "--directory", help="Directory to scan recursively for videos")
    parser.add_argument("-p", "--prefix", help="Converted files prefix",
            default="lgtv")
    parser.add_argument("file", nargs='*', help="Files to analyze")
    args = parser.parse_args()
    videos = scan_videos(dir=args.directory, file_list=args.file)
    for v in videos:
        get_subtitles(v)
    for v in videos:
        transcode_video(v, args.prefix)


if __name__ == '__main__':
    main(sys.argv)
