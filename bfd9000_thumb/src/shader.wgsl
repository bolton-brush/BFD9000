struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) color: vec4<f32>,
};

@vertex
fn vs_main(model: VertexInput) -> VertexOutput {
    var out: VertexOutput;

    // Quick isometric projection matrix rotation applied directly
    let cos_x = 0.866; // cos(30)
    let sin_x = 0.5;   // sin(30)
    let cos_z = 0.707; // cos(45)
    let sin_z = 0.707; // sin(45)

    // Rotate around Z, then X
    let x_rot = model.position.x * cos_z - model.position.y * sin_z;
    let y_temp = model.position.x * sin_z + model.position.y * cos_z;
    let y_rot = y_temp * cos_x - model.position.z * sin_x;
    let z_rot = y_temp * sin_x + model.position.z * cos_x;

    // Output scaled and offset to screen space
    out.clip_position = vec4<f32>(x_rot, y_rot, z_rot * 0.1, 1.0);

    // Simple directional shading based on the normal vector direction
    let light_dir = normalize(vec3<f32>(0.5, 0.5, 1.0));
    let dot_product = max(dot(normalize(model.normal), light_dir), 0.2);
    out.color = vec4<f32>(0.0, 0.4, 0.8, 1.0) * dot_product; // Shaded Blue

    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return in.color;
}
