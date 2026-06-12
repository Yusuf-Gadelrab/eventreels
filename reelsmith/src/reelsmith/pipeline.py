import logging
from typing import List
from . import analyze, select, render

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_reel(input_files: List[str], output_file: str, target_duration: float = 30.0):
    try:
        logger.info(f"Starting pipeline for {len(input_files)} clips.")
        
        all_segments = []
        energy_data = {}
        
        for i, f in enumerate(input_files):
            duration = analyze.duration_of(f)
            cuts = analyze.detect_scene_cuts(f)
            segs = select.build_segments(duration, cuts)
            
            # Simple motion-based energy for scoring
            energy = analyze.motion_energy(f)
            
            all_segments.extend(segs)
            energy_data[i] = energy
            
        # Select best segments
        selected = select.pick(all_segments, target_duration)
        
        # Render
        render.render(input_files, selected, output_file)
        
        logger.info(f"Pipeline complete: {output_file}")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise
