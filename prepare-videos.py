#!/usr/bin/python3

# Copyright 2016 Juan Orti Alcaine <j.orti.alcaine@gmail.com>
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


import sys
import os
import argparse
import subprocess
import subliminal
import babelfish
import json


class Video:
    """
    Video class has all the information of a video file.
    
    Properties:
    
    path
    directory
    filename
    basename
    extension
    info
    has_embedded_sub
    embedded_sub_id
    has_external_sub
    """
    def __init__(self, file_path):
        self.path = os.path.abspath(file_path)
        (self.directory, self.filename) = os.path.split(self.path)
        (self.basename, self.extension) = os.path.splitext(self.filename)
        self._scan_video()
        self._scan_embedded_subtitles()
        self._scan_external_subtitles()

    def _scan_video(self):
        try:
            info_json = subprocess.check_output(["ffprobe", "-show_format",
                                                 "-show_streams", "-loglevel", "quiet", "-print_format", "json",
                                                 self.path])
        except subprocess.CalledProcessError as ex:
            print(ex)
            sys.exit(1)
        self.info = json.loads(info_json.decode('utf_8'))

    def _scan_embedded_subtitles(self):
        self.has_embedded_sub = False
        for stream in self.info['streams']:
            if stream['codec_type'] == 'subtitle':
                self.has_embedded_sub = True
                self.embedded_sub_id = stream['index']
                return

    def _scan_external_subtitles(self):
        self.sub_path = os.path.join(self.directory, self.basename + ".srt")
        if os.path.isfile(self.sub_path):
            self.has_external_sub = True
        else:
            self.has_external_sub = False


def extract_embedded_sub(video):
    try:
        retval = subprocess.call(["mkvextract", "tracks", video.path,
                         str(video.embedded_sub_id) + ":" + video.sub_path])
        if retval == 0:
            print("Embedded subtitles successfully extracted.")
        else:
            print("ERROR: Embedded subtitles failed to extract, trying to download...")
            download_sub(video)
    except subprocess.CalledProcessError as ex:
        print("ERROR: Embedded subtitles failed to extract. ", ex)


def download_sub(video):
    try:
        v = subliminal.scan_video(video.path)
    except ValueError as ex:
        print("ERROR: Failed to analyze video video file. ", ex)
        return
    best_subs = subliminal.download_best_subtitles({v},
                                                   {babelfish.Language(OPTIONS.language)}, only_one=True)
    if best_subs[v]:
        sub = best_subs[v][0]
        subliminal.save_subtitles(v, [sub], single=True)
        print("Subtitles successfully downloaded.")
    else:
        print("ERROR: No subtitles found online.")


def get_subtitles(video):
    if not video.has_external_sub:
        print("External subtitles not present")
        if video.has_embedded_sub and not OPTIONS.download_subtitles:
            print("Extracting embedded subtitles...")
            extract_embedded_sub(video)
        else:
            print ("Downloading subtitles...")
            download_sub(video)
    else:
        print("External subtitles already present.")


def transcode_video(video):
    supported_vcodec = True
    supported_acodec = True
    for stream in video.info['streams']:
        if stream['codec_type'] == "video" and \
                        stream['codec_name'] in OPTIONS.unsupported_vcodecs:
            print("Unsupported video codec: {c}".format(c=stream['codec_name']))
            supported_vcodec = False
        if not (not (stream['codec_type'] == "audio") or not (stream['codec_name'] in OPTIONS.unsupported_acodecs)):
            print("Unsupported audio codec: {c}".format(c=stream['codec_name']))
            supported_acodec = False
    if not supported_vcodec or not supported_acodec:
        print("Transcoding...")
        target = os.path.join(video.directory, video.basename + "." + OPTIONS.container)
        original_dir = os.path.join(video.directory, ".original")
        original_file = os.path.join(original_dir, video.filename)
        if os.path.exists(original_file):
            print("{f} exists, cancelling transcoding.".format(f=original_file))
            return
        if not os.path.exists(original_dir):
            os.makedirs(original_dir)
        os.rename(video.path, original_file)
        if os.path.isfile(target):
            print("Skipping already converted video {f}".format(f=video.filename))
            return
        # ffmpeg -i file -nostats -loglevel 0 -c:v libx264 -preset slow -acodec copy -scodec copy h264-file
        command = ["ffmpeg", "-i", original_file, "-nostats", "-loglevel", "0"]
        if not supported_vcodec:
            command += ["-c:v", OPTIONS.vcodec, "-preset", "slow"]
        else:
            command += ["-vcodec", "copy"]
        if not supported_acodec:
            command += ["-c:a", OPTIONS.acodec]
        else:
            command += ["-acodec", "copy"]
        command += ["-scodec", "copy", target]
        print("Running command: {c}".format(c=command))
        try:
            retval = subprocess.call(command)
            print("OK: Video {f} transcoded".format(f=video.filename))
        except subprocess.CalledProcessError as ex:
            print("ERROR: Video {f} failed to transcode".format(f=video.filename))
            print(ex)
            return
        if retval != 0:
            print("ERROR: ffmpeg return value {v}".format(v=retval))
            if os.path.isfile(target):
                os.remove(target)
            return
        get_subtitles(Video(target))
    else:
        print("No transcoding needed.")


def is_supported_video_file(file):
    supported_extensions = frozenset(['.mkv', '.mp4', '.avi', '.mpg', '.mpeg', '.divx'])
    if os.path.isfile(file):
        (basename, ext) = os.path.splitext(file)
        if ext in supported_extensions:
            return True
    return False


def search_videos(directory=None, file_list=None):
    """Scan a directory for supported video files"""
    if not directory and not file_list:
        raise ValueError("A directory or a file must be specified")
    videos = []
    if directory:
        for root, dirs, files in os.walk(directory):
            for name in files:
                if os.path.basename(root) == ".original":
                    continue
                f = os.path.join(root, name)
                if is_supported_video_file(f):
                    videos.append(Video(f))
    if file_list:
        for f in file_list:
            if is_supported_video_file(f):
                videos.append(Video(f))
    return videos


def prepare_videos(videos):
    for v in videos:
        print("===========================")
        print("Processing video: {f}".format(f=v.filename))
        get_subtitles(v)
        transcode_video(v)
        print("")


def main():
    parser = argparse.ArgumentParser(description="Prepare videos for LG TV")
    parser.add_argument("-d", "--directory",
                        help="Directory to scan recursively for videos")
    parser.add_argument("-c", "--container",
                        help="Target video container (default: mkv)",
                        default="mkv")
    parser.add_argument("-vc", "--vcodec",
                        help="Target video codec (default: libx264)",
                        default="libx264")
    parser.add_argument("-ac", "--acodec",
                        help="Target audio codec (default: ac3)",
                        default="ac3")
    parser.add_argument("-uv", "--unsupported-vcodecs",
                        help="Unsupported video codecs (default: hevc)",
                        nargs='+',
                        default=["hevc"])
    parser.add_argument("-ua", "--unsupported-acodecs",
                        help="Unsupported audio codecs (default: dts, dca)",
                        nargs='+',
                        default=["dts", "dca"])
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="More information")
    parser.add_argument("-ds", "--download-subtitles", action="store_true",
                        help="Force to download subtitles")
    parser.add_argument("-l", "--language", help="Subtitles language",
                        default="eng")
    parser.add_argument("file", nargs='*', help="Files to analyze")
    global OPTIONS
    OPTIONS = parser.parse_args()
    videos = search_videos(directory=OPTIONS.directory, file_list=OPTIONS.file)
    prepare_videos(videos)


if __name__ == '__main__':
    main()
