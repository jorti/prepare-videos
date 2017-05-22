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
from subliminal import scan_video, download_best_subtitles, save_subtitles
import babelfish
import json
import logging


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
        command = ["ffprobe", "-show_format", "-show_streams", "-loglevel", "quiet", "-print_format", "json",
                   self.path]
        logging.debug("Running command {}".format(command))
        try:
            info_json = subprocess.check_output(command)
        except subprocess.CalledProcessError as ex:
            logging.critical("Failed tu run command {}".format(command))
            logging.critical(ex)
            sys.exit(1)
        except FileNotFoundError:
            logging.critical("Command ffprobe not found.")
            sys.exit(1)
        self.info = json.loads(info_json.decode('utf_8'))

    def _scan_embedded_subtitles(self):
        self.has_embedded_sub = False
        for stream in self.info['streams']:
            if stream['codec_type'] == 'subtitle' and stream['codec_name'] == 'subrip':
                self.has_embedded_sub = True
                self.embedded_sub_id = stream['index']
                break

    def _scan_external_subtitles(self):
        self.sub_path = os.path.join(self.directory, self.basename + ".srt")
        if os.path.isfile(self.sub_path):
            self.has_external_sub = True
        else:
            self.has_external_sub = False


def extract_embedded_sub(video):
    command = ["mkvextract", "tracks", video.path, str(video.embedded_sub_id) + ":" + video.sub_path]
    logging.debug("Running command {}".format(command))
    try:
        retval = subprocess.call(command)
        if retval == 0:
            logging.info("{}: Embedded subtitles successfully extracted.".format(video.filename))
        else:
            logging.error("{}: Embedded subtitles failed to extract, trying to download...".format(video.filename))
            download_sub(video)
    except subprocess.CalledProcessError as ex:
        logging.error("{}: Embedded subtitles failed to extract.".format(video.filename))
        logging.error("ex")
    except FileNotFoundError:
        logging.critical("Command mkvextract not found.")
        sys.exit(1)


def download_sub(video):
    try:
        v = scan_video(video.path)
    except ValueError as ex:
        logging.error("{}: Failed to analyze file".format(video.filename))
        logging.error(ex)
        return
    best_subs = download_best_subtitles({v},
                                        {babelfish.Language(args.language)}, only_one=True)
    if best_subs[v]:
        sub = best_subs[v][0]
        save_subtitles(v, [sub], single=True)
        logging.info("{}: Subtitles successfully downloaded.".format(video.filename))
    else:
        logging.error("{}: No subtitles found online.".format(video.filename))


def get_subtitles(video):
    if not video.has_external_sub:
        logging.warning("{}: External subtitles not present".format(video.filename))
        if video.has_embedded_sub and not args.download_subtitles:
            logging.info("{}: Extracting embedded subtitles...".format(video.filename))
            extract_embedded_sub(video)
        else:
            logging.info("{}: Downloading subtitles...".format(video.filename))
            download_sub(video)
    else:
        logging.info("{}: External subtitles already present.".format(video.filename))


def transcode_video(video):
    supported_video_codec = True
    supported_audio_codec = True
    for stream in video.info['streams']:
        if stream['codec_type'] == "video" and \
                        stream['codec_name'] in args.unsupported_video_codecs:
            logging.warning("{v}: Unsupported video codec: {c}".format(v=video.filename, c=stream['codec_name']))
            supported_video_codec = False
        if not (not (stream['codec_type'] == "audio") or not (stream['codec_name'] in args.unsupported_audio_codecs)):
            logging.warning("{v}: Unsupported audio codec: {c}".format(v=video.filename, c=stream['codec_name']))
            supported_audio_codec = False
    if not supported_video_codec or not supported_audio_codec:
        logging.info("{}: Transcoding...".format(video.filename))
        target = os.path.join(video.directory, video.basename + "." + args.container)
        original_dir = os.path.join(video.directory, ".original")
        original_file = os.path.join(original_dir, video.filename)
        if os.path.exists(original_file):
            logging.info("{f} exists, cancelling transcoding.".format(f=original_file))
            return
        if not os.path.exists(original_dir):
            os.makedirs(original_dir)
        os.rename(video.path, original_file)
        if os.path.isfile(target):
            logging.info("{}: Skipping already converted video file".format(video.filename))
            return
        # ffmpeg -i file -nostats -loglevel 0 -c:v libx264 -preset slow -acodec copy -scodec copy h264-file
        command = ["ffmpeg", "-i", original_file, "-nostats", "-loglevel", "0"]
        if not supported_video_codec:
            command += ["-c:v", args.vcodec, "-preset", "slow"]
        else:
            command += ["-vcodec", "copy"]
        if not supported_audio_codec:
            command += ["-c:a", args.audio_codec]
        else:
            command += ["-acodec", "copy"]
        command += ["-scodec", "copy", target]
        logging.debug("Running command {}".format(command))
        try:
            retval = subprocess.call(command)
            logging.info("{}: Transcoded successfully".format(video.filename))
        except subprocess.CalledProcessError as ex:
            logging.error("{}: failed to transcode".format(video.filename))
            logging.error(ex)
            return
        except FileNotFoundError:
            logging.critical("Command ffmpeg not found.")
            sys.exit(1)
        if retval != 0:
            logging.error("{v}: ffmpeg return value {r}".format(v=video.filename, r=retval))
            if os.path.isfile(target):
                os.remove(target)
            return
        get_subtitles(Video(target))
    else:
        logging.info("{}: No transcoding needed.".format(video.filename))


def is_supported_video_file(file):
    supported_extensions = frozenset(['.mkv', '.mp4', '.avi', '.mpg', '.mpeg', '.divx'])
    if os.path.isfile(file):
        (basename, ext) = os.path.splitext(file)
        if ext in supported_extensions:
            return True
    return False


def search_videos(directory, files):
    """Scan a directory for supported video files"""
    if not directory and not files:
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
    if files:
        for f in files:
            if is_supported_video_file(f):
                videos.append(Video(f))
    return videos


parser = argparse.ArgumentParser(
    description='Script to prepare video files: download subtitles, transcode to supported formats, etc.')
parser.add_argument("-d", "--directory",
                    help="Directory to scan recursively for videos")
parser.add_argument("-c", "--container",
                    help="Target video container (default: mkv)",
                    default="mkv")
parser.add_argument("-vc", "--vcodec",
                    help="Target video codec (default: libx264)",
                    default="libx264")
parser.add_argument("-ac", "--audio-codec",
                    help="Target audio codec (default: ac3)",
                    default="ac3")
parser.add_argument("-uv", "--unsupported-video-codecs",
                    help="Unsupported video codecs (default: hevc)",
                    nargs='+',
                    default=["hevc"])
parser.add_argument("-ua", "--unsupported-audio-codecs",
                    help="Unsupported audio codecs (default: dts, dca)",
                    nargs='+',
                    default=["dts", "dca"])
parser.add_argument("--log-level", default="WARNING", help="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
parser.add_argument("-ds", "--download-subtitles", action="store_true",
                    help="Force to download subtitles")
parser.add_argument("-l", "--language", help="Subtitles language",
                    default="eng")
parser.add_argument("file", nargs='*', help="Files to analyze")
args = parser.parse_args()
logging.basicConfig(level=args.log_level.upper())
logging.getLogger("subliminal").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("rebulk").setLevel(logging.WARNING)
try:
    videos = search_videos(directory=args.directory, files=args.file)
except ValueError:
    logging.critical("Please, specify at least a file or a directory.")
    sys.exit(1)
for v in videos:
    logging.info("{}: Processing video".format(v.filename))
    get_subtitles(v)
    transcode_video(v)
