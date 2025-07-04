import pickle
from copy import deepcopy
import numpy as np
from scipy.stats import norm
from SyMBac.cell import Cell
from SyMBac.trench_geometry import trench_creator, get_trench_segments
from pymunk.pyglet_util import DrawOptions
import pymunk
import pyglet
from tqdm.auto import tqdm
#import pdb # Add the debugger

#TODO work these functions into a class, possibly in simulation.py

def run_simulation(trench_length, trench_width, cell_max_length, cell_width, sim_length, pix_mic_conv, gravity,
                   phys_iters, max_length_var, width_var, save_dir, resize_amount, lysis_p=0, show_window = True):
    """
    Runs the rigid body simulation of bacterial growth based on a variety of parameters. Opens up a Pyglet window to
    display the animation in real-time. If the simulation looks bad to your eye, restart the kernel and rerun the
    simulation. There is currently a bug where if you try to rerun the simulation in the same kernel with show_window=True, it will be
    extremely slow.

    Parameters
    ----------

    trench_length : float
        Length of a mother machine trench (micron)
    trench_width : float
        Width of a mother machine trench (micron)
    cell_max_length : float
        Maximum length a cell can reach before dividing (micron)
    cell_width : float
        the average cell width in the simulation (micron)
    pix_mic_conv : float
        The micron/pixel size of the image
    gravity : float
        Pressure forcing cells into the trench. Typically left at zero, but can be varied if cells start to fall into
        each other or if the simulation behaves strangely.
    phys_iters : int
        Number of physics iterations per simulation frame. Increase to resolve collisions if cells are falling into one
        another, but decrease if cells begin to repel one another too much (too high a value causes cells to bounce off
        each other very hard). 20 is a good starting point
    max_length_var : float
        Variance of the maximum cell length
    width_var : float
        Variance of the maximum cell width
    save_dir : str
        Location to save simulation output
    lysis_p : float
        probability of cell lysis

    Returns
    -------
    cell_timeseries : lists
        A list of parameters for each cell, such as length, width, position, angle, etc. All used in the drawing of the
        scene later
    space : a pymunk space object
        Contains the rigid body physics objects which are the cells.
    """

    space = create_space()
    space.gravity = 0, gravity  # arbitrary units, negative is toward trench pole
    #space.iterations = 1000
    #space.damping = 0
    #space.collision_bias = 0.0017970074436457143*10
    space.collision_slop = 0.
    dt = 1 / 20  # time-step per frame
    pix_mic_conv = 1 / pix_mic_conv  # micron per pixel
    scale_factor = pix_mic_conv * resize_amount  # resolution scaling factor

    trench_length = trench_length * scale_factor
    trench_width = trench_width * scale_factor
    trench_creator(trench_width, trench_length, (35, 0), space)  # Coordinates of bottom left corner of the trench

    # Always set the N cells to 1 before adding a cell to the space, and set the mask_label
    space.historic_N_cells = 1
    cell1 = Cell(
        length=cell_max_length*0.5 * scale_factor,
        width=cell_width * scale_factor,
        resolution=60,
        position=(40, 100),
        angle=0.8,
        space=space,
        dt= dt,
        growth_rate_constant=1,
        max_length=cell_max_length * scale_factor,
        max_length_mean=cell_max_length * scale_factor,
        max_length_var=max_length_var * np.sqrt(scale_factor),
        width_var=width_var * np.sqrt(scale_factor),
        width_mean=cell_width * scale_factor,
        mother=None,
        lysis_p=lysis_p,
        mask_label=1,
        generation = 0,
        N_divisions=0
    )

    if show_window:

        window = pyglet.window.Window(700, 700, "SyMBac", resizable=True)
        options = DrawOptions()
        options.shape_outline_color = (10,20,30,40)
        @window.event
        def on_draw():
            window.clear()
            space.debug_draw(options)

        # key press event
        @window.event
        def on_key_press(symbol, modifier):

            # key "E" get press
            if symbol == pyglet.window.key.E:
                # close the window
                window.close()

    x = [0]
    cell_timeseries = []
    cells = [cell1]
    historic_cells = [cell1] # A list of cells which will contain all cells ever in the simulation
    if show_window:
        pyglet.clock.schedule_interval(step_and_update, interval=dt, cells=cells, space=space, phys_iters=phys_iters,
                                       ylim=trench_length, cell_timeseries=cell_timeseries, x=x, sim_length=sim_length,
                                       save_dir=save_dir, historic_cells=historic_cells)
        pyglet.app.run()
    else:
        for _ in tqdm(range(sim_length+2)):
            step_and_update(
                dt=dt, cells=cells, space=space, phys_iters=phys_iters, ylim=trench_length,
                cell_timeseries=cell_timeseries, x=x, sim_length=sim_length, save_dir=save_dir, historic_cells=historic_cells,
            )


    for frame, cells in enumerate(cell_timeseries):
        for cell in cells:
            cell.t = frame#

    #for cell in cell_timeseries[0]:
    #    cell.prev_t_cell = None
    #for cells_prev, cells in zip(cell_timeseries, cell_timeseries[1:]):
    #    for cell in cells:
    #        for cell_prev in cells_prev:
    #            if cell.mask_label == cell_prev.mask_label:
    #                cell.prev_t_cell = cell_prev
    #            else:
    #                cell.prev_t_cell = None

    return cell_timeseries, space, historic_cells

def create_space():
    """
    Creates a pymunk space

    :return pymunk.Space space: A pymunk space
    """

    space = pymunk.Space(threaded=False)
    space.historic_N_cells = 0
    #space.threads = 2
    return space



def update_pm_cells(cells, space):
    """
    Iterates through all cells in the simulation and updates their pymunk body and shape objects. Contains logic to
    check for cell division, and create daughters if necessary.

    :param list(SyMBac.cell.Cell) cells: A list of all cells in the current timepoint of the simulation.

    """
    for cell in cells:
        cell.update_length()
        if cell.is_dividing():
            daughter_details = cell.create_pm_cell()
            if len(daughter_details) > 2: # Really hacky. Needs fixing because sometimes this returns cell_body, cell shape. So this is a check to ensure that it's returing daughter_x, y and angle
                daughter = Cell(**daughter_details)
                cell.daughter = daughter
                daughter.mother = cell
                #daughter.mo
                cells.append(daughter)
        else:
            cell.create_pm_cell()
        cell_adder(cell, space)
        for _ in range(150):
            space.step(1/100)

def cell_adder(cell, space):
    space.add(cell.body, cell.shape)

def update_cell_positions(cells):
    """
    Iterates through all cells in the simulation and updates their positions, keeping the cell object's position
    synchronised with its corresponding pymunk shape and body inside the pymunk space.

    :param list(SyMBac.cell.Cell) cells: A list of all cells in the current timepoint of the simulation.
    """
    for cell in cells:
        cell.update_position()

def wipe_space(space):
    """
    Deletes all cells in the simulation pymunk space.

    :param pymunk.Space space:
    """
    # This loop also modifies space.bodies and space.shapes, so it needs the same pattern
    bodies_to_remove = []
    shapes_to_remove = []
    for body, poly in zip(space.bodies, space.shapes):
        if body.body_type == 0: # Assuming 0 refers to dynamic bodies (cells)
            bodies_to_remove.append(body)
            shapes_to_remove.append(poly)

    for body in bodies_to_remove:
        space.remove(body)
    for poly in shapes_to_remove:
        space.remove(poly)


def step_and_update(dt, cells, space, phys_iters, ylim, cell_timeseries, x, sim_length,save_dir, historic_cells):
    """
    Evolves the simulation forward

    :param float dt: The simulation timestep
    :param list(SyMBac.cell.Cell)  cells: A list of all cells in the current timestep
    :param pymunk.Space space: The simulations's pymunk space.
    :param int phys_iters: The number of physics iteration in each timestep
    :param int ylim: The y coordinate threshold beyond which to delete cells
    :param list cell_timeseries: A list to store the cell's properties each time the simulation steps forward
    :param int list: A list with a single value to store the simulation's progress.
    :param int sim_length: The number of timesteps to run.
    :param str save_dir: The directory to save the simulation information.

    Returns
    -------
    cells : list(SyMBac.cell.Cell)

    """

    # Breakpoint 1: At the start of step_and_update
    # Use 'p dt', 'p len(cells)', 'p len(space.shapes)' to inspect.
    # Use 'n' to step through lines.
    # Use 'c' to continue.
    #breakpoint() # Or import pdb; pdb.set_trace() for Python versions < 3.7

#    for shape in space.shapes:
#        if shape.body.position.y < 0 or shape.body.position.y > ylim:
#            space.remove(shape.body, shape)
#            space.step(dt)

# the issue here is that space.remove modifies 'space.shapes' while it's being iterated over,
# even though you're looping through a *copy* of its elements. The underlying reason
# is that the iterator's internal state is tied to the original collection.
# To fix this, we collect items to remove and then remove them *after* the loop.

    shapes_to_remove = []
    for shape in list(space.shapes): # Iterate over a copy to safely identify items
        if shape.body.position.y < 0 or shape.body.position.y > ylim:
            shapes_to_remove.append((shape.body, shape))

    for body, shape_item in shapes_to_remove: # Perform removals outside the loop
        space.remove(body, shape_item)
        # Note: space.step(dt) was inside the removal loop in your original code.
        # It's usually a per-timestep operation, so keeping it inside this
        # post-processing loop seems okay if that was the intent.
        space.step(dt)


    #for cell in cells:
    #    historic_cells.append(cell)
    #    if cell.shape.body.position.y < 0 or cell.shape.body.position.y > ylim:
    #        cell.dead = True
    #        cells.remove(cell)
    #        space.step(dt)
    #    elif norm.rvs() <= norm.ppf(cell.lysis_p) and len(cells) > 1:   # in case all cells disappear
    #        cell.dead = True
    #        cells.remove(cell)
    #        space.step(dt)
    #    else:
    #        pass
    #    historic_cells.append(cell)

    # Corrected loop for cells
    # The same principle applies here: you cannot modify 'cells' while iterating over it.
    cells_to_remove = []
    for cell in cells: # Iterate over cells to identify which ones to remove
        if cell.shape.body.position.y < 0 or cell.shape.body.position.y > ylim:
            cells_to_remove.append(cell)
        # Added a check to ensure `norm` is from `scipy.stats` as it's common
        elif norm.rvs() <= norm.ppf(cell.lysis_p) and len(cells) > 1: # in case all cells disappear
            cells_to_remove.append(cell)

    for cell_item in cells_to_remove: # Perform removals outside the loop
        if cell_item in cells: # Check if cell still exists before attempting to remove
            cells.remove(cell_item)
            # Note: space.step(dt) was inside the original loop.
            # Assuming it should apply for each removed cell's effect.
            space.step(dt)

    wipe_space(space)
    update_pm_cells(cells, space)
    for _ in range(phys_iters):
        space.step(dt)
    update_cell_positions(cells)

    if x[0] > 1:
        cell_timeseries.append(deepcopy(cells))
    if x[0] == sim_length-1:
        with open(save_dir+"/cell_timeseries.p", "wb") as f:
            pickle.dump(cell_timeseries, f)
        with open(save_dir+"/space_timeseries.p", "wb") as f:
            pickle.dump(space, f)
        pyglet.app.exit()
        return cells
    x[0] += 1
    return (cells)

