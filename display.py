import os
import webbrowser
import random
from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass
class DataInfo:
    """Consolidated metadata for a specific data item."""
    hover: str
    color: str
    label: str

class Display:
    def __init__(self, N: int, S: int):
        """
        Initialize the Display.
        
        Args:
            N (int): Number of parallel tracks (columns).
            S (int): Number of segments (rows).
        """
        self.N = N
        self.S = S
        self.updates = [] # List of tuples: (resolved_data, summary_text)
        
    def update(self, data: Dict[int, List[Any]], datainfos: Dict[Any, DataInfo], summary: str = ""):
        """
        Add a new segment of data.
        
        Args:
            data (dict): A map of track_key (int) -> list[Any items].
            datainfos (dict): A map of item (Any) -> DataInfo for this update.
            summary (str): Summary text to display in the row index cell.
        """
        if len(self.updates) >= self.S:
            print("Warning: Maximum number of segments (S) reached. Update ignored.")
            return

        # Resolve the metadata for each item in each track immediately
        resolved_segment = {}
        for track_id, items in data.items():
            resolved_items = []
            for item in items:
                # Look up the DataInfo in the provided map
                info = datainfos.get(item)
                if info:
                    resolved_items.append(info)
                else:
                    # Fallback for unknown items
                    resolved_items.append(DataInfo(
                        hover=f"Unknown item: {item}", 
                        color="#ccc", 
                        label="?"
                    ))
            resolved_segment[track_id] = resolved_items

        self.updates.append((resolved_segment, summary))

    def _generate_css(self):
        return f"""
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f4f4f9;
                margin: 0;
                padding: 20px;
                color: #333;
            }}
            h1 {{
                text-align: center;
                color: #444;
            }}
            /* The Main Grid Container */
            .grid-container {{
                display: grid;
                /* 1st column for Row Index + Summary, then N columns for tracks */
                grid-template-columns: 120px repeat({self.N}, 1fr); 
                gap: 0;
                background-color: #fff;
                border: 1px solid #ccc;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                max-width: 100%;
            }}
            
            /* Header Cells */
            .track-header {{
                background-color: #e0e0e0;
                padding: 10px;
                text-align: center;
                font-weight: bold;
                border-bottom: 2px solid #ccc;
                border-right: 1px solid #ddd;
            }}

            /* Data Cells */
            .cell {{
                padding: 8px;
                border-bottom: 1px solid #eee;
                border-right: 1px solid #eee;
                min-height: 50px;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}

            /* Grouped Row: Forces a new line for each label group */
            .label-group {{
                display: flex;
                flex-direction: row;
                flex-wrap: wrap; 
                width: 100%;
                gap: 5px;
            }}

            /* Index Column Style */
            .index-cell {{
                background-color: #f9f9f9;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: 5px;
                border-bottom: 1px solid #eee;
                border-right: 2px solid #ccc;
                text-align: center;
            }}
            
            .row-number {{
                font-weight: bold;
                font-size: 1.1em;
                color: #333;
            }}
            
            .row-summary {{
                font-size: 0.75em;
                color: #666;
                margin-top: 4px;
                line-height: 1.2;
                word-break: break-word;
            }}
            
            .cell:hover {{
                background-color: #fafafa;
            }}

            .circle {{
                width: 22px;
                height: 22px;
                border-radius: 50%;
                border: 1px solid rgba(0,0,0,0.2);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 11px;
                text-shadow: 0px 0px 1px rgba(0,0,0,0.5);
                transition: transform 0.1s, box-shadow 0.1s;
                cursor: help;
                user-select: none;
            }}
            
            .circle:hover {{
                transform: scale(1.3);
                z-index: 10;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);
            }}

            /* Last column border cleanup */
            .cell:nth-child({self.N + 1}n) {{
                border-right: none;
            }}
        </style>
        """

    def render(self, filename="/tmp/output.html"):
        """
        Generates the HTML file and opens it.
        """
        track_keys = list(range(-1, self.N - 1))

        html_content = [
            "<!DOCTYPE html>", "<html>", "<head>", 
            "<meta charset='UTF-8'>", "<title>Data Visualization</title>"
        ]
        html_content.append(self._generate_css())
        html_content.append("</head><body>")
        html_content.append("<h1>System Status Tracks</h1>")

        html_content.append('<div class="grid-container">')

        # Headers
        html_content.append('<div class="track-header"># / Summary</div>')
        for key in track_keys:
            html_content.append(f'<div class="track-header">{key}</div>')

        # Rows (Segments)
        for segment_idx, (resolved_data, summary) in enumerate(self.updates):
            # 1. Row Index + Summary Cell
            html_content.append(f'''
                <div class="index-cell">
                    <div class="row-number">{segment_idx}</div>
                    <div class="row-summary">{summary}</div>
                </div>
            ''')
            
            # 2. Track Data Cells
            for track_key in track_keys:
                # Get the pre-resolved DataInfo objects for this track
                resolved_items = resolved_data.get(track_key, [])
                html_content.append(f'<div class="cell" title="Segment {segment_idx}, Track {track_key}">')
                
                # Group resolved info by label
                groups = {}
                for info in resolved_items:
                    label = info.label
                    if label not in groups:
                        groups[label] = []
                    groups[label].append(info)
                
                # Render groups
                for label in sorted(groups.keys()):
                    html_content.append('<div class="label-group">')
                    for info in groups[label]:
                        circle_html = (
                            f'<div class="circle" '
                            f'style="background-color: {info.color};" '
                            f'title="{info.hover}">{info.label}</div>'
                        )
                        html_content.append(circle_html)
                    html_content.append('</div>')
                
                html_content.append('</div>')

        html_content.append('</div></body></html>')

        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
        except Exception:
            pass

        with open(filename, "w", encoding='utf-8') as f:
            f.write("\n".join(html_content))
        
        abs_path = os.path.abspath(filename)
#         print(f"Successfully generated HTML report: {abs_path}")
#         webbrowser.open(f"file://{abs_path}")

def main():
    # --- Configuration ---
    # We can now use strings or any hashable type as data keys
    CODE_CPU = "proc_load"
    CODE_MEM = "memory_use"
    CODE_IO  = "disk_io"
    CODE_NET = "network"
    CODE_ERR = "error"

    # Define the mapping once, though it could change per update if needed
    current_infos = {
        CODE_CPU: DataInfo(hover="CPU High Load", color="#FF6B6B", label="C"),
        CODE_MEM: DataInfo(hover="Memory Allocation", color="#4ECDC4", label="M"),
        CODE_IO:  DataInfo(hover="Disk Write", color="#E67E22", label="I"),
        CODE_NET: DataInfo(hover="Network Packet", color="#2980B9", label="N"),
        CODE_ERR: DataInfo(hover="Critical Error", color="#2C3E50", label="X")
    }

    N = 5
    S = 8
    display = Display(N=N, S=S)

    summaries = [
        "System Startup", "Peak Traffic", "Batch Processing", "Normal Operation",
        "Backup Started", "Maintenance", "Network Spike", "Cooldown"
    ]

    track_ids = list(range(-1, N - 1))
    
    for i in range(S):
        data_update = {}
        for tid in track_ids:
            num_events = random.randint(5, 20) 
            # Pick from our generic string keys
            events = [random.choice(list(current_infos.keys())) for _ in range(num_events)]
            data_update[tid] = events
            
        display.update(data_update, datainfos=current_infos, summary=summaries[i % len(summaries)])

    display.render()

if __name__ == "__main__":
    main()
