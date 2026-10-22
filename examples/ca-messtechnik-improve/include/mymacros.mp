  if unknown context_back : input mp-form; fi;

  vardef qrcode(expr tmp) =
    save value;
    save lx;
    save ly;
    string value; value := tmp;%
    image(
      lua("userdata.generate_qrmatrix(mp.get.string('value'))");
    )
  enddef;

  vardef squaredblock(expr Width, Height, Unit) =
    save vlines;
    save hlines;
    save width;
    save height;
    numeric vlines; vlines := floor(Width/Unit);
    numeric hlines; hlines := floor(Height/Unit);
    numeric width; width  := vlines*Unit;
    numeric height; height := hlines*Unit;
    drawoptions(withpen pencircle scaled 0.3pt withcolor .0white);
    image(
      draw hlingrid(0, hlines, 1, height, width);
      draw vlingrid(0, vlines, 1, width, height);
    )
  enddef;

  vardef trunc expr f =
    save r; numeric r;
    if f < 0 : r = ceiling(f);
    else: r = floor(f);
    fi;
    r
  enddef;

  vardef drawemptydot expr z =
    save circle; path circle; circle = fullcircle scaled 3bp shifted z;
    unfill circle;
    draw circle;
  enddef;

  vardef drawemptydotnew (expr z, r) =
    save circle; path circle;
    circle = fullcircle scaled (r) shifted z;
    unfill circle;
    draw circle;
  enddef;

  vardef xtick (expr l, z) =
    save tick; path tick;
    tick := ((0, -l) -- (0, l)) shifted z;
    tick
  enddef;

  vardef ytick (expr l, z) =
    save tick; path tick;
    tick := ((-l, 0) -- (l, 0)) shifted z;
    tick
  enddef;

  vardef tick.x (expr l, z) =
    save tick; path tick;
    tick := ((0, -l) -- (0, l)) shifted z;
    tick
  enddef;

  vardef tick.y (expr l, z) =
    save tick; path tick;
    tick := ((-l, 0) -- (l, 0)) shifted z;
    tick
  enddef;

 vardef curvedarrow (expr x, y) =
    save curve, pnt;
    path curve;
    pair pnt;
    pnt := 0.1[x,y] shifted -x rotated 270 shifted (0.5[x,y]);
    curve := (x .. pnt .. y);
    curve
  enddef;

  vardef doublearrow (expr x, y, Text) =
    save pnt, pntx, pnty, s;
    pair pnt;
    pair pntx;
    pair pnty;
    picture s;
    pnt := 0.5[x, y];
    s := textext(Text) shifted pnt;
    pntx := (outerboundingbox s) intersectionpoint (pnt -- x);
    pnty := (outerboundingbox s) intersectionpoint (pnt -- y);
    drawarrow (pntx -- x);
    drawarrow (pnty -- y);
    draw s;
  enddef;

  vardef outerdoublearrow (expr x, y, l) =
    save p, q;
    path p;
    path q;
    p := (x -- y);
    q := (y -- x);
    image(
      drawarrow leftarrow (p,point 1 of p, l) shifted (x-y);
      drawarrow leftarrow (q,point 1 of q, l) shifted (y-x);
    )
  enddef;

  vardef draw_car(expr p, n, r, len, name) =
    % p : an arbitrary path
    % n : a point on p (ie "point n of p" should exist)
    % r : the radius of the car's wheels
    % len : the length of the car's body
    save a, b, q, t; path q; pair a, b; transform t;
    % construct a path q, parallel to the given path p starting at point n of p
    q = for i = n step 0.1 until length(p)+eps:
      point i of p + ((0,r) rotated angle direction i of p) ..
    endfor
    point infinity of p + ((0,r) rotated angle direction infinity of p);
    % a = center of back wheel, b = center of front wheel
    a = point 0 of q;
    b = q intersectionpoint fullcircle scaled 2 len shifted a;
    % draw the wheels
    fill fullcircle scaled 2r shifted a;
    fill fullcircle scaled 2r shifted b;
    % draw the body of the truck with a label, suitably transformed
    t = identity rotated angle (b-a) shifted a;
    draw unitsquare xscaled len yscaled 13/21 len transformed t;
    picture M; M = image(label(name,(1/2len,1/3len))); draw M transformed t;
    enddef;

  vardef draw_human(expr p, n, r, size, name) =
    % p : an arbitrary path
    % n : a point on p (ie "point n of p" should exist)
    % r : the radius of the human's head
    % size : the size of the human without head
    save a, b, q, t; path q; pair a, b; transform t;
    % construct a path q, parallel to the given path p starting at point n of p
    q = for i = n step 0.1 until length(p)+eps:
      point i of p ..
    endfor
    point infinity of p;
    % a = center of back wheel, b = center of front wheel
    a = point 0 of q;
    b = q intersectionpoint fullcircle scaled 26/21 size shifted a;
    % draw the body of the truck with a label, suitably transformed
    t = identity rotated angle (b-a) shifted a;
    % draw the head
    fill fullcircle scaled 2r shifted (13/42 size, r+size) transformed t;
    % draw the body of the truck with a label, suitably transformed
    draw unitsquare xscaled 13/21 size yscaled size transformed t;
    picture M; M = image(label(name,(1/3size,1/2size))); draw M transformed t;
    enddef;

  %%%%%%%%%%%%%%%%%%
  %% boundingbox is:
  %% bottomleft(0,0)
  %% topright(2,5)
  %% head has center at (1,4.5)
  %%%%%%%%%%%%%%%%%%
  def human =
  image(
      draw ((0,0)--(1,2)--(2,0));
      draw ((0,2.5)--(1,4)--(2,2.5));
      draw ((1,2)--(1,4));
      draw (fullcircle shifted (1,4.5));
  )
  enddef;


  %%%%%%%%%%%%%%%%%%
  %% draw oszilloscope screen scaled by factor u
  %%%%%%%%%%%%%%%%%%
  vardef oszilloscope (expr u) =
  image(
    %draw horizontal divisions
    for i=-4 step 1 until 4 :
      draw ((-5,i)--(5,i)) scaled u;
    endfor;

    %draw vertical divisions
    for i=-5 step 1 until 5 :
      draw ((i,-4)--(i,4)) scaled u;
    endfor;

    %draw horizontal subdivisions
    for i=-4 step 0.2 until 4 :
      if abs(i - round(i)) > 0.1:
        draw ytick(0.1, (0, i)) scaled u;
      fi;
    endfor;

    %draw vertical subdivisions
    for i=-5 step 0.2 until 5 :
      if abs(i - round(i)) > 0.1:
        draw xtick(0.1, (i, 0)) scaled u;
      fi;
    endfor;

    %draw 0% and 100% lines
    for i=-5 step 0.2 until 5 :
      if abs(i - round(i)) > 0.1:
        draw ytick(0.05, (i,  2.5)) scaled u;
        draw ytick(0.05, (i, -2.5)) scaled u;
      fi;
    endfor;
  )
  enddef;


  %%%%%%%%%%%%%%%%%%
  %% draw resistor symbol scaled by factor u
  %% connection points from (-3u,0u) to (3u,0u)
  %%%%%%%%%%%%%%%%%%
  vardef resistor(expr u) =
    image(
      draw ((-1.5,-0.5)--(-1.5,0.5)--(1.5,0.5)--(1.5,-0.5)--cycle) scaled u;
      draw ((-3,0)--(-1.5,0)) scaled u;
      draw ((1.5,0)--(3,0)) scaled u;
    )
  enddef;


  %%%%%%%%%%%%%%%%%%
  %% draw capacitor symbol scaled by factor u
  %% connection points from (-2u,0u) to (2u,0u)
  %%%%%%%%%%%%%%%%%%
  vardef capacitor(expr u) =
    image(
      draw ((-0.2,1)--(-0.2,-1)) scaled u;
      draw ((0.2,1)--(0.2,-1)) scaled u;
      draw ((-2,0)--(-0.2,0)) scaled u;
      draw ((0.2,0)--(2,0)) scaled u;
    )
  enddef;


  %%%%%%%%%%%%%%%%%%
  %% draw coil symbol scaled by factor u
  %% connection points from (-3u,0u) to (3u,0u)
  %%%%%%%%%%%%%%%%%%
  vardef coil(expr u) =
    image(
      draw halfcircle shifted (-1.5,0) scaled .75u;
      draw halfcircle shifted (-0.5,0) scaled .75u;
      draw halfcircle shifted (0.5,0) scaled .75u;
      draw halfcircle shifted (1.5,0) scaled .75u;
      draw ((-3,0)--(-1.5,0)) scaled u;
      draw ((1.5,0)--(3,0)) scaled u;
    )
  enddef;



  %%%%%%%%%%%%%%%%%%
  %% boundingbox is:
  %% bottomleft(0, -(Extension+Length)*u)
  %% topright(Width*u, Width*u/2 + Width*u/4)
  %% example: draw springscale(cm, 1, 5, 0.08, 3, 0.3, 75);
  %%%%%%%%%%%%%%%%%%
  vardef springscale (expr u, Width, Length, Edge, Extension, Scale, Maxforce) =
    save p, Measurewidth, Measurescale, S, SS, SSsmall, SSlarge;
    path p;

    Measurewidth := (Width-2*Edge)*u;
    Measurescale := Scale*u;
    p := ((Width/2, -Extension-Length) -- (Width/2, -Length)) scaled u;
    z.S = (Width/2, -Extension-Length) scaled u;
    z.SS = z.S shifted (Measurewidth/2, 0);
    z.SSsmall = (x.SS -  Width*u/8, y.SS);
    z.SSlarge = (x.SS -  Width*u/4, y.SS);


    image(
      linecap:=butt;
      draw p withpen pencircle scaled Measurewidth dashed dashpattern(on 1 off 1) scaled Measurescale withcolor .8white;
      linecap:=rounded;
      draw (p shifted (Measurewidth/2, 0)) -- (reverse p shifted (-Measurewidth/2, 0)) -- cycle;
      draw ((0, 0)--(Width, 0)--(Width, -Length)--(0, -Length)--cycle) scaled u;
      draw ((Width/2, 0) -- (Width/2, Width/4)) scaled u;
      draw fullcircle scaled (Width*u/2) shifted (Width*u/2, Width*u/2);

      imax := Extension*10/Scale;

      for i=0 step 1 until imax :
        draw (z.SS --
            (if (i mod 5) = 0 : z.SSlarge else : z.SSsmall fi))
            shifted (0, i*Measurescale/10) withpen pencircle scaled 0.1mm;
      endfor;

      imax := Extension/Scale;

%      for i=1 step 1 until imax :
%        label(decimal(i*Maxforce/10), z.S shifted (0, (i-0.5)*Measurescale));
%      endfor;

      label("" & decimal(Maxforce) & "N", (Width*u/2, -0.5*Measurescale));
    )
  enddef;
