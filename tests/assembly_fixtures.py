"""Small synthetic original clips; never read a production data directory."""
from mmv import final_assembly
from mmv.storage import write_json


def source_recipe(directory, make_video, width=128, height=72):
    raw = directory / 'original-clip.mkv'
    make_video(raw)
    recipe = {'clips': [{'path': str(raw), 'frames': 144}], 'frames': 144,
              'width': width, 'height': height, 'fps': 24,
              'audio': [{'path': str(raw), 'frames': 144}]}
    write_json(directory / final_assembly.RECIPE, recipe)
    final_assembly.render(recipe, directory / 'music-video.mp4')
    return recipe
