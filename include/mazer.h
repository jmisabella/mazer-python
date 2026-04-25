#ifndef MAZER_H
#define MAZER_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>   // for size_t
#include <stdint.h>   // for int32_t
#include <stdbool.h>  // for bool

/* Opaque type declarations.
 * The actual definitions of these types are hidden from the Swift side.
 */
typedef struct Grid Grid;

typedef struct FFICell {
    size_t x;
    size_t y;
    const char* maze_type;
    const char** linked;
    size_t linked_len;
    int32_t distance;
    bool is_start;
    bool is_goal;
    bool is_active;
    bool is_visited;
    bool has_been_visited;
    bool on_solution_path;
    const char* orientation;
    bool is_square;
} FFICell;

/**
 * Generates a maze from a JSON request.
 *
 * This function takes a null-terminated JSON string representing the maze generation
 * request and attempts to generate a maze. On success, it returns a pointer to a newly
 * allocated Grid instance. In case of an error (such as an invalid JSON or a failure in
 * maze generation), it returns NULL.
 *
 * @param request_json A null-terminated C string containing the JSON request.
 * @return A pointer to the generated Grid if successful, or NULL on failure.
 */
Grid* mazer_generate_maze(const char *request_json);

/**
 * Destroys a maze instance.
 *
 * This function deallocates the memory and any associated resources for the given maze (Grid).
 * If the provided maze pointer is NULL, the function does nothing.
 *
 * @param maze A pointer to the Grid instance to be destroyed.
 */
void mazer_destroy(Grid *maze);

/**
 * Retrieves the cells of the maze.
 *
 * This function returns an array of FFICell structures that represent the individual cells
 * of the maze. It also writes the number of cells into the provided 'length' pointer.
 *
 * @param maze A pointer to the Grid whose cells are to be retrieved.
 * @param length A pointer to a size_t variable where the function will store the number of cells.
 * @return A pointer to an array of FFICell structures, or NULL if the input pointers are invalid.
 */
FFICell* mazer_get_cells(Grid *maze, size_t *length);

/**
 * Frees an array of FFICell.
 *
 * This function deallocates the memory allocated for an array of FFICell structures that was
 * previously returned by mazer_get_cells. The 'length' parameter must match the number of
 * elements in the array.
 *
 * @param ptr A pointer to the array of FFICell to be freed.
 * @param length The number of FFICell elements in the array.
 */
void mazer_free_cells(FFICell *ptr, size_t length);

/**
 * Retrieves the number of generation steps for the maze.
 *
 * This function returns the number of intermediate grid states recorded during maze generation
 * if the capture_steps feature is enabled. If capture_steps is not enabled or if the grid pointer
 * is invalid, it returns 0.
 *
 * @param grid A pointer to the Grid instance.
 * @return The number of generation steps, or 0 if capture_steps is not enabled or the grid is invalid.
 */
size_t mazer_get_generation_steps_count(Grid *grid);

/**
 * Retrieves the cells for a specific generation step of the maze.
 *
 * This function returns an array of FFICell structures representing the cells of the maze at a
 * specific step in the generation process. It also writes the number of cells into the provided
 * 'length' pointer.
 *
 * @param grid A pointer to the Grid instance.
 * @param step_index The index of the generation step to retrieve.
 * @param length A pointer to a size_t variable where the function will store the number of cells.
 * @return A pointer to an array of FFICell structures for the specified step, or NULL if the input
 *         pointers are invalid or the step index is out of range.
 */
FFICell* mazer_get_generation_step_cells(Grid *grid, size_t step_index, size_t *length);

/**
 * Updates the maze by performing a move in the specified direction.
 *
 * This function takes an opaque pointer to the mutable Grid and a null-terminated
 * C string that indicates the direction for the move. It calls the internal `make_move`
 * function on the Grid instance and returns an updated opaque pointer.
 *
 * @param grid_ptr A pointer to the mutable Grid.
 * @param direction A null-terminated C string indicating the move direction.
 * @return A pointer to the updated `Grid` instance if successful, or a null pointer if an error occurs.
 */
void* mazer_make_move(void* grid_ptr, const char* direction);

/**
 * Retrieves the number of generation steps for the maze.
 *
 * This function returns the number of intermediate grid states recorded during maze generation
 * if the capture_steps feature is enabled. If capture_steps is not enabled or if the grid pointer
 * is invalid, it returns 0.
 *
 * @param grid A pointer to the Grid instance.
 * @return The number of generation steps, or 0 if capture_steps is not enabled or the grid is invalid.
 */
size_t mazer_get_generation_steps_count(Grid *grid);

/**
 * Retrieves the cells for a specific generation step of the maze.
 *
 * This function returns an array of FFICell structures representing the cells of the maze at a
 * specific step in the generation process. It also writes the number of cells into the provided
 * 'length' pointer.
 *
 * @param grid A pointer to the Grid instance.
 * @param step_index The index of the generation step to retrieve.
 * @param length A pointer to a size_t variable where the function will store the number of cells.
 * @return A pointer to an array of FFICell structures for the specified step, or NULL if the input
 *         pointers are invalid or the step index is out of range.
 */
FFICell* mazer_get_generation_step_cells(Grid *grid, size_t step_index, size_t *length);

/**
 * To verify FFI connectivity, call verify this returns 42.
 */
int mazer_ffi_integration_test();

#ifdef __cplusplus
}
#endif

#endif /* MAZER_H */
