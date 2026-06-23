use crate::OutputFormat;
use bytemuck::{Pod, Zeroable};
use image::{ImageBuffer, ImageFormat, Rgba};
use std::io;
use wgpu::util::DeviceExt;

#[repr(C)]
#[derive(Copy, Clone, Debug, Pod, Zeroable)]
struct Vertex {
    position: [f32; 3],
    normal: [f32; 3],
}

pub fn render_stl(
    input_bytes: &[u8],
    width: u32,
    height: u32,
    format: OutputFormat,
) -> Result<Vec<u8>, String> {
    let mesh = stl_io::read_stl(&mut io::Cursor::new(input_bytes))
        .map_err(|e| format!("Failed to parse STL layout: {}", e))?;

    if mesh.vertices.is_empty() {
        return Err("The parsed STL model contains zero vertices.".to_string());
    }

    // Find the Bounding Box of the Mesh
    let mut min_x = f32::INFINITY;
    let mut max_x = f32::NEG_INFINITY;
    let mut min_y = f32::INFINITY;
    let mut max_y = f32::NEG_INFINITY;
    let mut min_z = f32::INFINITY;
    let mut max_z = f32::NEG_INFINITY;

    for v in &mesh.vertices {
        if v[0] < min_x {
            min_x = v[0];
        }
        if v[0] > max_x {
            max_x = v[0];
        }
        if v[1] < min_y {
            min_y = v[1];
        }
        if v[1] > max_y {
            max_y = v[1];
        }
        if v[2] < min_z {
            min_z = v[2];
        }
        if v[2] > max_z {
            max_z = v[2];
        }
    }

    let center_x = (min_x + max_x) / 2.0;
    let center_y = (min_y + max_y) / 2.0;
    let center_z = (min_z + max_z) / 2.0;

    let size_x = max_x - min_x;
    let size_y = max_y - min_y;
    let size_z = max_z - min_z;

    // Find the maximum dimension to normalize scale
    let max_dimension = size_x.max(size_y).max(size_z);

    let scale = if max_dimension > 0.0 {
        1.1 / max_dimension
    } else {
        1.0
    };

    // Transform mesh
    let mut vertex_data = Vec::new();
    for face in mesh.faces {
        let normal = [face.normal[0], face.normal[1], face.normal[2]];
        for &v_idx in &face.vertices {
            let v = mesh.vertices[v_idx];

            // Apply normalization transformations
            let norm_x = (v[0] - center_x) * scale;
            let norm_y = (v[1] - center_y) * scale;
            let norm_z = (v[2] - center_z) * scale;

            vertex_data.push(Vertex {
                position: [norm_x, norm_y, norm_z],
                normal,
            });
        }
    }

    let instance = wgpu::Instance::default();
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::None,
        compatible_surface: None,
        force_fallback_adapter: false,
    }))
    .ok_or("Failed to discover an isolated headless graphics adapter")?;

    let (device, queue) = pollster::block_on(adapter.request_device(
        &wgpu::DeviceDescriptor {
            label: None,
            required_features: wgpu::Features::empty(),
            required_limits: wgpu::Limits::default(),
            memory_hints: wgpu::MemoryHints::default(),
        },
        None,
    ))
    .map_err(|e| format!("Failed to initialize logical WGPU device: {}", e))?;

    let bytes_per_pixel = std::mem::size_of::<u32>() as u32;
    let unpadded_bytes_per_row = width * bytes_per_pixel;
    let align = wgpu::COPY_BYTES_PER_ROW_ALIGNMENT;
    let padding = (align - unpadded_bytes_per_row % align) % align;
    let padded_bytes_per_row = unpadded_bytes_per_row + padding;

    let texture_desc = wgpu::TextureDescriptor {
        size: wgpu::Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8UnormSrgb,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
        label: None,
        view_formats: &[],
    };
    let texture = device.create_texture(&texture_desc);
    let texture_view = texture.create_view(&wgpu::TextureViewDescriptor::default());

    let output_buffer_desc = wgpu::BufferDescriptor {
        size: (padded_bytes_per_row * height) as wgpu::BufferAddress,
        usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
        label: None,
        mapped_at_creation: false,
    };
    let output_buffer = device.create_buffer(&output_buffer_desc);

    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("Shader"),
        source: wgpu::ShaderSource::Wgsl(include_str!("shader.wgsl").into()),
    });

    let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("Vertex Buffer"),
        contents: bytemuck::cast_slice(&vertex_data),
        usage: wgpu::BufferUsages::VERTEX,
    });

    let render_pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: None,
        bind_group_layouts: &[],
        push_constant_ranges: &[],
    });

    let render_pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: None,
        layout: Some(&render_pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: Some("vs_main"),
            buffers: &[wgpu::VertexBufferLayout {
                array_stride: std::mem::size_of::<Vertex>() as wgpu::BufferAddress,
                step_mode: wgpu::VertexStepMode::Vertex,
                attributes: &wgpu::vertex_attr_array![0 => Float32x3, 1 => Float32x3],
            }],
            compilation_options: Default::default(),
        },
        fragment: Some(wgpu::FragmentState {
            module: &shader,
            entry_point: Some("fs_main"),
            targets: &[Some(wgpu::ColorTargetState {
                format: texture_desc.format,
                blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                write_mask: wgpu::ColorWrites::ALL,
            })],
            compilation_options: Default::default(),
        }),
        primitive: wgpu::PrimitiveState {
            topology: wgpu::PrimitiveTopology::TriangleList,
            ..Default::default()
        },
        depth_stencil: None,
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    });

    let mut encoder =
        device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: None });
    {
        let mut render_pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: None,
            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                view: &texture_view,
                resolve_target: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Clear(wgpu::Color {
                        r: 1.0,
                        g: 1.0,
                        b: 1.0,
                        a: 0.0,
                    }),
                    store: wgpu::StoreOp::Store,
                },
            })],
            depth_stencil_attachment: None,
            timestamp_writes: None,
            occlusion_query_set: None,
        });
        render_pass.set_pipeline(&render_pipeline);
        render_pass.set_vertex_buffer(0, vertex_buffer.slice(..));
        render_pass.draw(0..vertex_data.len() as u32, 0..1);
    }

    encoder.copy_texture_to_buffer(
        wgpu::TexelCopyTextureInfo {
            texture: &texture,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        wgpu::TexelCopyBufferInfo {
            buffer: &output_buffer,
            layout: wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(padded_bytes_per_row),
                rows_per_image: Some(height),
            },
        },
        texture_desc.size,
    );

    queue.submit(Some(encoder.finish()));

    // Map and Extract Raw Memory (Unpadding layout loops)
    let buffer_slice = output_buffer.slice(..);
    let (tx, rx) = std::sync::mpsc::channel();
    buffer_slice.map_async(wgpu::MapMode::Read, move |result| {
        tx.send(result).unwrap();
    });
    device.poll(wgpu::Maintain::Wait);
    rx.recv()
        .unwrap()
        .map_err(|e| format!("Buffer map async error: {}", e))?;

    let data = buffer_slice.get_mapped_range();
    let mut img_buf: ImageBuffer<Rgba<u8>, Vec<u8>> = ImageBuffer::new(width, height);

    for row in 0..height {
        let start = (row * padded_bytes_per_row) as usize;
        let end = start + (width * bytes_per_pixel) as usize;
        let row_data = &data[start..end];

        for (col, chunk) in row_data.chunks_exact(4).enumerate() {
            img_buf.put_pixel(
                col as u32,
                row,
                Rgba([chunk[0], chunk[1], chunk[2], chunk[3]]),
            );
        }
    }
    drop(data);

    // Route and serialize target image compression style mapping
    let mut output_bytes = Vec::new();

    let target_format = match format {
        OutputFormat::Png => ImageFormat::Png,
        OutputFormat::Webp => ImageFormat::WebP,
    };

    img_buf
        .write_to(&mut io::Cursor::new(&mut output_bytes), target_format)
        .map_err(|e| format!("Failed to compress image data: {}", e))?;

    Ok(output_bytes)
}
