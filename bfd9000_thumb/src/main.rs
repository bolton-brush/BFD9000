mod renderer;

use clap::{Parser, ValueEnum};
use std::fs::File;
use std::io::{self, Read, Write};
use std::path::PathBuf;

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq)]
pub enum OutputFormat {
    Png,
    Webp,
}

#[derive(Parser, Debug)]
#[command(author, version, about = "Headless WGPU STL Thumbnail Generator")]
struct Args {
    #[arg(
        short,
        long,
        help = "Path to input STL file (Omitting reads from STDIN)"
    )]
    input: Option<PathBuf>,

    #[arg(
        short,
        long,
        help = "Path to output image file (Omitting writes to STDOUT)"
    )]
    output: Option<PathBuf>,

    #[arg(
        short,
        long,
        default_value_t = 256,
        help = "Width of the output thumbnail"
    )]
    width: u32,

    #[arg(long, default_value_t = 256, help = "Height of the output thumbnail")]
    height: u32,

    #[arg(short, long, value_enum, default_value_t = OutputFormat::Png, help = "Target encoding compression format")]
    format: OutputFormat,
}

fn main() {
    let args = Args::parse();

    let mut input_buffer = Vec::new();
    if let Some(path) = args.input {
        let mut file = File::open(path).expect("Failed to open specified input file");
        file.read_to_end(&mut input_buffer)
            .expect("Failed to read file");
    } else {
        io::stdin()
            .read_to_end(&mut input_buffer)
            .expect("Failed to read from STDIN");
    }

    let output_bytes =
        match renderer::render_stl(&input_buffer, args.width, args.height, args.format) {
            Ok(bytes) => bytes,
            Err(err_msg) => {
                eprintln!("Graphics Render Pipeline Error: {}", err_msg);
                std::process::exit(1);
            }
        };

    if let Some(path) = args.output {
        let mut file = File::create(path).expect("Failed to generate target output asset on disk");
        file.write_all(&output_bytes)
            .expect("Failed writing data payload to storage destination");
    } else {
        let mut stdout = io::stdout().lock();
        stdout
            .write_all(&output_bytes)
            .expect("Failed writing streaming raw binary block to process STDOUT");
    }
}
