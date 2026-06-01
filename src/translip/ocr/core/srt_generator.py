"""SRT generator module - generates SRT format subtitle files"""

from typing import List
import logging

from translip.ocr.models.domain import Subtitle

logger = logging.getLogger(__name__)


class SRTGenerator:
    """SRT subtitle file generator"""

    @staticmethod
    def generate(subtitles: List[Subtitle]) -> str:
        """
        Generate SRT format subtitle content

        Args:
            subtitles: List of subtitles

        Returns:
            SRT format string
        """
        srt_lines = []

        for sub in subtitles:
            srt_lines.append(sub.to_srt_format())

        return '\n'.join(srt_lines)

    @staticmethod
    def save_to_file(subtitles: List[Subtitle], output_path: str) -> str:
        """
        Save SRT file

        Args:
            subtitles: List of subtitles
            output_path: Output file path

        Returns:
            Saved file path
        """
        srt_content = SRTGenerator.generate(subtitles)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)

        logger.info(f"SRT file saved to: {output_path}")
        return output_path

    @staticmethod
    def seconds_to_srt_time(seconds: float) -> str:
        """
        Convert seconds to SRT time format

        Args:
            seconds: Time in seconds

        Returns:
            SRT time string HH:MM:SS,mmm
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def srt_time_to_seconds(srt_time: str) -> float:
        """
        Convert SRT time format to seconds

        Args:
            srt_time: SRT time string HH:MM:SS,mmm

        Returns:
            Time in seconds
        """
        parts = srt_time.replace(',', ':').split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        millis = int(parts[3]) if len(parts) > 3 else 0

        return hours * 3600 + minutes * 60 + seconds + millis / 1000

    @staticmethod
    def parse_srt(srt_content: str) -> List[Subtitle]:
        """
        Parse SRT content to subtitle list

        Args:
            srt_content: SRT format string

        Returns:
            List of Subtitle objects
        """
        subtitles = []
        blocks = srt_content.strip().split('\n\n')

        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                try:
                    index = int(lines[0])
                    time_line = lines[1]
                    text = '\n'.join(lines[2:])

                    # Parse time line: HH:MM:SS,mmm --> HH:MM:SS,mmm
                    times = time_line.split(' --> ')
                    if len(times) == 2:
                        start_time = SRTGenerator.srt_time_to_seconds(times[0].strip())
                        end_time = SRTGenerator.srt_time_to_seconds(times[1].strip())

                        subtitle = Subtitle(
                            index=index,
                            start_time=start_time,
                            end_time=end_time,
                            text=text,
                            confidence=1.0
                        )
                        subtitles.append(subtitle)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse SRT block: {block[:50]}... Error: {e}")
                    continue

        return subtitles