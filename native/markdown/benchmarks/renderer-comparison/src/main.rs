use std::hint::black_box;
use std::time::Instant;
use std::{env, fs};

fn main() {
    let args = env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 4 {
        eprintln!("usage: upstream-renderer SPEC WARMUPS ITERATIONS REPEATS");
        std::process::exit(2);
    }

    let source = fs::read_to_string(&args[0]).expect("failed to read input");
    let warmups = args[1].parse::<usize>().expect("invalid warmup count");
    let iterations = args[2].parse::<usize>().expect("invalid iteration count");
    let repeats = args[3].parse::<usize>().expect("invalid repeat count");

    let mut markdown = markdown_it::MarkdownIt::new();
    markdown_it::plugins::cmark::add(&mut markdown);
    markdown_it::plugins::html::add(&mut markdown);

    let mut output_bytes = 0;
    for _ in 0..warmups {
        let output = markdown.parse(&source).render();
        output_bytes = output.len();
        black_box(output);
    }

    let mut samples_ms = Vec::with_capacity(repeats);
    let mut checksum = 0;
    for _ in 0..repeats {
        let started_at = Instant::now();
        for _ in 0..iterations {
            let output = markdown.parse(&source).render();
            output_bytes = output.len();
            checksum += output_bytes;
            black_box(output);
        }
        samples_ms.push(started_at.elapsed().as_secs_f64() * 1000.0 / iterations as f64);
    }

    let samples = samples_ms
        .iter()
        .map(|sample| format!("{sample:.9}"))
        .collect::<Vec<_>>()
        .join(",");
    println!(
        "{{\"engine\":\"markdown-it-rs upstream\",\"version\":\"0.7.0 workspace\",\"samples_ms\":[{samples}],\"output_bytes\":{output_bytes},\"checksum\":{checksum}}}"
    );
}
