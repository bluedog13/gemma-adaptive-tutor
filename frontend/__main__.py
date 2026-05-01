"""Entry point for running the Gradio frontend: python -m frontend."""

from frontend.app import custom_css, custom_head, demo, theme

demo.launch(server_port=7860, theme=theme, css=custom_css, head=custom_head)
